import asyncio
import json
import os
import time
from typing import List, Dict

from agno.agent import Agent
from agno.workflow import RunResponse, Workflow
from agno.utils.log import logger

from agents.report_search_agent import ReportSearchAgent
from agents.report_analyze_agent import ReportAnalyzeAgent

from models.report_url import ReportURL

from unstructured.partition.auto import partition
from unstructured.chunking.basic import chunk_elements
from unstructured.cleaners.core import clean
from unstructured.cleaners.core import group_broken_paragraphs
from unstructured.cleaners.core import clean_non_ascii_chars


MAX_CHARACTERS = int(os.getenv("CHUNK_MAX_CHARACTERS", "10000"))
OVERLAP = int(os.getenv("CHUNK_OVERLAP", "0"))


class InsidersWorkflow(Workflow):
    """
    A multi agent workflow designed to search and ingest corporate governance report data into a knowledge graph
    """

    def __init__(self):
        super().__init__()
        self.max_concurrent = 5
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self.report_search_agent: Agent = ReportSearchAgent()
        self.report_analyze_agent: Agent = ReportAnalyzeAgent()

    def run(self, company_name: str) -> RunResponse:
        """
        Run the workflow for a target company.

        Args:
            company_name (str): The name of the target company.
        """

        return asyncio.run(self._run_async(company_name))

    async def _run_async(self, company_name: str) -> RunResponse:
        try:
            # Search the report
            logger.info(f"Searching report...")
            report_url: ReportURL = self.report_search_agent.search_report(company_name)
            logger.info(f"Found report at {report_url.url}")
        except Exception as e:
            logger.error(str(e))
            return RunResponse(
                content=f"Sorry, unable to find governance report for '{company_name}'."
            )

        if report_url.url is None or report_url.url == "":
            logger.warning(f"Report url is empty.")
            return RunResponse(
                content=f"Sorry, unable to find governance report for '{company_name}'."
            )

        try:
            # Partition the report
            logger.info("Partitioning report...")
            elements = partition(url=report_url.url)
            logger.info(
                f"Report partitioned successfully. Number of elements: {len(elements)}"
            )
        except Exception as e:
            logger.error(str(e))
            return RunResponse(
                content=f"Sorry, unable to partition report at {report_url.url}"
            )

        # Clean text
        for el in elements:
            el.apply(
                lambda x: clean(x, bullets=True, extra_whitespace=True, dashes=True)
            )
            el.apply(group_broken_paragraphs)
            el.apply(clean_non_ascii_chars)

        try:
            # Chunks the elements
            logger.info(
                f"Chunking elements (max_characters: {MAX_CHARACTERS}, overlap: {OVERLAP})..."
            )
            chunks = chunk_elements(
                elements, max_characters=MAX_CHARACTERS, overlap=OVERLAP
            )
            logger.info(
                f"Elements chunked successfully. Number of chunks: {len(chunks)}"
            )
        except Exception as e:
            logger.error(str(e))
            return RunResponse(content="Sorry, unable to chunk report elements.")

        # Analyze chunks
        start_time = time.time()
        chunks_results = await self._process_chunks_batch(chunks)
        end_time = time.time()
        analysis_duration = end_time - start_time

        success_chunks = [chunk for chunk in chunks_results if chunk.get("result")]
        error_chunks = [chunk for chunk in chunks_results if chunk.get("error")]
        logger.info(
            f"Chunk analysis completed in {analysis_duration:.2f} seconds. Total chunks: {len(chunks_results)}. Success: {len(success_chunks)}. Failed: {len(error_chunks)}"
        )

        final_result = self._collect_chunks_results(success_chunks)

        return RunResponse(content=final_result)

    async def _process_chunks_batch(self, chunks) -> List[Dict]:
        """
        Process chunks in batches with concurrency control.

        Args:
            chunks: List of chunks to process.

        Returns:
            List[Dict]: List of results for each chunk.
        """
        tasks = [
            self._analyze_chunk_with_semaphore(index, chunk)
            for index, chunk in enumerate(chunks)
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _analyze_chunk_with_semaphore(self, index: int, chunk) -> Dict:
        async with self.semaphore:
            try:
                logger.info(f"Processing chunk {index}...")
                res = await self.report_analyze_agent.analyze_chunk_async(chunk.text)
                return {"chunk_index": index, "result": res}
            except KeyboardInterrupt as e:
                logger.error("Process interrupted by user.")
                raise e
            except Exception as e:
                logger.error(f"Errpr processing chunk {index}: {str(e)}")
                return {"chunk_index": index, "error": str(e)}

    def _collect_chunks_results(self, chunks_results) -> Dict:
        """
        Collects the results from all chunk analyses.

        Args:
            chunks_results: List of results from chunk analyses.

        Returns:
            Dict: Aggregated results.
        """

        def update_properties(new_props, old_props):
            for key, value in new_props.items():
                if key in old_props:
                    old_value = old_props[key]
                    if isinstance(value, str) and isinstance(old_value, str):
                        old_props[key] = max(old_props[key], value, key=len)
                    else:
                        old_props[key] = value
                else:
                    old_props[key] = value

        final_result = {"nodes": {}, "edges": []}

        for res in chunks_results:
            result_data = res.get("result")  # This is a ReportResultsTemp instance

            # Access Pydantic model attributes directly
            nodes = result_data.nodes  # List[Node]
            edges = result_data.edges  # List[Edge]

            # Process nodes
            for node in nodes:
                node_id = node.id
                if node_id:
                    if node_id in final_result["nodes"]:
                        # Update existing node properties
                        update_properties(
                            node.properties,
                            final_result["nodes"][node_id]["properties"],
                        )
                    else:
                        final_result["nodes"][node_id] = {
                            "id": node.id,
                            "label": node.label,
                            "properties": node.properties.copy(),
                        }

            # Process edges
            for edge in edges:
                edge_dict = {
                    "source": edge.source,
                    "type": edge.type,
                    "dest": edge.dest,
                    "properties": edge.properties,
                }

                # Check if edge already exists (same source, target, label)
                edge_exists = False
                for existing_edge in final_result["edges"]:
                    if (
                        existing_edge["source"] == edge.source
                        and existing_edge["type"] == edge.type
                        and existing_edge["dest"] == edge.dest
                    ):
                        # Update properties of existing edge
                        update_properties(edge.properties, existing_edge["properties"])
                        edge_exists = True
                        break

                if not edge_exists:
                    final_result["edges"].append(edge_dict)

        # Convert nodes dict back to list for final result
        final_result["nodes"] = list(final_result["nodes"].values())

        return final_result
