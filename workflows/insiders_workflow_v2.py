import os
import tempfile
import time
import asyncio

from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse

from agno.agent import Agent
from agno.workflow import RunResponse, Workflow
from agno.utils.log import logger

from agents.report_search_agent import ReportSearchAgent
from agents.report_analyze_agent import ReportAnalyzeAgent
from agents.validation_agent import ValidationAgent

from models.report import Report

from db.driver import DBDriver
from exceptions.exceptions import WorkflowException

from unstructured.partition.auto import partition
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.html import partition_html
from unstructured.chunking.basic import chunk_elements
from unstructured.cleaners.core import clean
from unstructured.cleaners.core import group_broken_paragraphs
from unstructured.cleaners.core import clean_non_ascii_chars

from models.report_results import ReportResultsTemp

from thefuzz import fuzz
from playwright.async_api import async_playwright


class InsidersWorkflow(Workflow):
    """
    A multi agent workflow designed to search and ingest corporate governance report data into a knowledge graph.
    """

    def __init__(self):
        super().__init__()
        self.max_characters = 45000
        self.overlap = 100
        self.similarity_threshold = 90
        self.max_concurrent = 5
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self.report_search_agent: Agent = ReportSearchAgent()
        self.report_analyze_agent: Agent = ReportAnalyzeAgent()
        self.validation_agent: Agent = ValidationAgent()
        self.db = self._get_db_driver()

    def _get_db_driver(self) -> DBDriver:
        """
        Initialize and return the database driver.

        Returns:
            DBDriver: The initialized database driver.
        """
        try:
            db = DBDriver()
            return db
        except Exception as e:
            message = f"Error initializing database driver."
            raise WorkflowException(message) from e

    def run(self, company_name: str) -> RunResponse:
        """
        Run the workflow for a target company.

        Args:
            company_name (str): The name of the target company.

        Returns:
            RunResponse: The response of the workflow containing the summarized results or error message.
        """

        return asyncio.run(self._run_async(company_name))

    async def _run_async(self, company_name: str) -> RunResponse:
        """
        Steps:

        1. Search for the corporate governance report URL.
        2. If URL found, partition the report into elements.
        3. Chunk the elements.
        4. Analyze each chunk concurrently with a semaphore to limit concurrency.
        5. Summarize the results from all chunks.
        """

        logger.info(f"Searching report for '{company_name}'...")

        report_url = self._get_report_url(company_name)
        if not report_url:
            message = (
                f"Unable to find report for '{company_name}'. Report URL is empty."
            )
            raise WorkflowException(message)

        logger.info(f"Found report URL: {report_url}")
        answer = input(
            f"Do you want to proceed with the analysis? [Y/n] "
        )  # Asks the user for confirmation to proceed
        if not answer.lower() in ["y", "yes"]:
            return RunResponse(content="")  # Return empty response if user declines

        logger.info(f"Processing report...")

        tmp_file_path = await self._download_report(report_url)

        elements = self._partition_report(tmp_file_path)
        logger.info(f"Partitioned report into {len(elements)} elements.")

        self._clean_elements(elements)
        logger.info(f"Cleaned report elements.")

        chunks = self._chunk_elements(elements)
        logger.info(f"Chunked report into {len(chunks)} chunks.")

        logger.info(f"Processing chunks with max concurrency {self.max_concurrent}...")

        start_time = time.time()
        chunks_results = await self._process_chunks(chunks)  # Analyze chunks in batches
        end_time = time.time()

        analysis_duration = end_time - start_time
        success_chunks = [chunk for chunk in chunks_results if chunk.get("result")]

        logger.info(
            f"Chunk analysis completed in {analysis_duration:.2f} seconds. \
                Total chunks: {len(chunks_results)}. Success: {len(success_chunks)}. Failed: {len(chunks_results) - len(success_chunks)}"
        )

        # logger.info(f"Summarizing results from {len(success_chunks)} successful chunks...")
        # summarized_results: ReportResultsTemp = self._summarize_results([c.get("result") for c in success_chunks if c.get("result")])  # Summarize only successful chunk results
        # return RunResponse(content=summarized_results)

        merged_results = self._collect_chunks_results(success_chunks)

        logger.info(
            f"Merged results from chunks. Nodes: {len(merged_results['nodes'])}, Edges: {len(merged_results['edges'])}"
        )

        logger.info(f"Validating final results...")
        final_results: ReportResultsTemp = self._validate_results(merged_results)

        logger.info(
            f"Final results validated. Nodes: {len(final_results.nodes)}, Edges: {len(final_results.edges)}"
        )

        self._add_source_to_results(final_results, report_url)

        answer = input(f"Do you want to save the results to the database? [Y/n] ")
        if answer.lower() in ["y", "yes"]:
            self.db.save_report_results(final_results)
            self.db.close()
            logger.info(f"Results saved to the database.")

        return RunResponse(content=final_results)

    def _get_report_url(self, company_name: str) -> str:
        try:
            report: Report = self.report_search_agent.search_report(company_name)
            return report.url
        except Exception as e:
            message = f"Unable to find governance report for '{company_name}'."
            raise WorkflowException(message) from e

    async def _download_report(self, report_url: str) -> str:
        """
        Download the report using Playwright Async API and save to a temporary file.
        Returns the temp file path.
        """
        tmp_file_path = None
        origin = f"{urlparse(report_url).scheme}://{urlparse(report_url).netloc}"

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
                )
                page = await context.new_page()
                
                # Try a navigation to detect WAF/challenge (don't rely on it for PDF body)
                resp = None
                try:
                    resp = await page.goto(report_url, wait_until="networkidle", timeout=30000)
                except Exception as e:
                    # navigation for PDF often raises ERR_ABORTED; swallow and continue to detection/fetch
                    logger.debug(f"page.goto initial attempt failed/aborted: {e}")
                    resp = None

                # inspect page HTML to detect common WAF/challenge markers
                try:
                    html = await page.content()
                except Exception:
                    html = ""

                def _is_challenge(resp, html_str: str) -> bool:
                    if "_Incapsula_Resource" in html_str or "visid_incap" in html_str or "captcha" in html_str.lower():
                        return True
                    if resp is not None:
                        status = getattr(resp, "status", None)
                        if status in (403, 429):
                            return True
                        ctype = (resp.headers.get("content-type") or "").lower()
                        if "text/html" in ctype and ("_Incapsula_Resource" in html_str or "Request unsuccessful" in html_str):
                            return True
                    return False

                if _is_challenge(resp, html):
                    logger.info(f"WAF/challenge detected for {report_url}, doing origin pre-flight {origin}")
                    try:
                        await page.goto(origin, wait_until="networkidle", timeout=45000)
                        for pth in ["/", "/en", "/it"]:
                            try:
                                await page.goto(origin.rstrip("/") + pth, wait_until="networkidle", timeout=20000)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(f"Pre-flight origin visit failed: {e}")

                # Prefer context.request.get to fetch the raw resource (works for PDFs)
                response = None
                try:
                    response = await context.request.get(report_url, timeout=60000)
                except Exception as e:
                    logger.debug(f"context.request.get failed: {e}")
                    response = None

                data = None
                suffix = ""
                if response is not None and 200 <= response.status < 300:
                    ctype = (response.headers.get("content-type") or "").lower()
                    if "application/pdf" in ctype or report_url.lower().endswith(".pdf"):
                        data = await response.body()
                        suffix = ".pdf"
                    elif "text/html" in ctype or report_url.lower().endswith(".html"):
                        txt = await response.text()
                        data = txt.encode("utf-8")
                        suffix = ".html"
                    else:
                        # fallback to body
                        try:
                            data = await response.body()
                        except Exception:
                            txt = await response.text()
                            data = txt.encode("utf-8")
                else:
                    # Last-resort fallback: try a lighter navigation and grab page content
                    try:
                        resp2 = await page.goto(report_url, wait_until="domcontentloaded", timeout=30000)
                        # try to detect pdf by headers if present
                        ctype = ""
                        if resp2 is not None:
                            ctype = (resp2.headers.get("content-type") or "").lower()
                        if resp2 is not None and "application/pdf" in ctype:
                            data = await resp2.body()
                            suffix = ".pdf"
                        else:
                            html2 = await page.content()
                            data = html2.encode("utf-8")
                            suffix = ".html"
                    except Exception as e:
                        raise WorkflowException(f"Unable to fetch report after retries: {e}") from e

                # write to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                    tmp_file.write(data or b"")
                    tmp_file_path = tmp_file.name

                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass
        except Exception as e:
            raise WorkflowException(f"Unable to download report: {e}") from e

        if not tmp_file_path:
            raise WorkflowException(f"Unable to download report: no file created for {report_url}")
        return tmp_file_path

    def _partition_report(self, tmp_file_path: str) -> List:
        try:
            if tmp_file_path.endswith(".pdf"):
                elements = partition_pdf(filename=tmp_file_path)
            elif tmp_file_path.endswith(".html"):
                elements = partition_html(filename=tmp_file_path)
            else:
                elements = partition(filename=tmp_file_path)
            return elements
        except Exception as e:
            message = f"Sorry, unable to partition report at {tmp_file_path}: {str(e)}"
            raise WorkflowException(message) from e
        finally:
            try:
                if tmp_file_path and os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
            except Exception:
                pass

    def _clean_elements(self, elements: List) -> None:
        try:
            for (
                el
            ) in elements:  # Remove unwanted characters and group broken paragraphs
                el.apply(
                    lambda x: clean(x, bullets=True, extra_whitespace=True, dashes=True)
                )
                el.apply(group_broken_paragraphs)
                el.apply(clean_non_ascii_chars)
        except Exception as e:
            message = f"Error cleaning report elements."
            raise WorkflowException(message) from e

    def _chunk_elements(self, elements: List) -> List:
        try:
            chunks = chunk_elements(
                elements, max_characters=self.max_characters, overlap=self.overlap
            )
            return chunks
        except Exception as e:
            message = f"Error chunking report elements."
            raise WorkflowException(message) from e

    async def _process_chunks(self, chunks) -> List[Dict]:
        tasks = [
            self._analyze_chunk_with_semaphore(index, chunk)
            for index, chunk in enumerate(chunks)
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _analyze_chunk_with_semaphore(self, index: int, chunk) -> Dict:
        async with self.semaphore:
            try:
                res = await self.report_analyze_agent.analyze_chunk_async(
                    index, chunk.text
                )
                print(f"""\n{'='*100}\n{res}""")

                return {"chunk_index": index, "result": res}
            except KeyboardInterrupt as e:
                logger.error("Process interrupted by user.")
                raise e
            except Exception as e:
                logger.error(f"Errpr processing chunk {index}: {str(e)}")
                return {"chunk_index": index, "error": str(e)}

    def _summarize_results(self, chunks_results: List[str]) -> ReportResultsTemp:
        retries = 3
        for attempt in range(retries):
            try:
                res = self.summarization_agent.summarize_results(chunks_results)
                return res
            except Exception as e:
                if attempt < retries - 1:
                    message = f"Error summarizing results (attempt {attempt + 1}): {str(e)}. Retrying..."
                    logger.warning(message)
                else:
                    message = "Max retries reached. Unable to summarize results."
                    raise WorkflowException(message) from e

    def _get_node_comparison_string(self, node: Dict) -> str:
        """Crea una stringa rappresentativa per un nodo per il confronto."""
        props = node["properties"]
        label = node["label"]

        if label == "Insider":
            return f"{props.get('firstName', '')} {props.get('lastName', '')}".lower().strip()
        elif label == "Company":
            return props.get("name", "").lower().strip()
        elif label in ["Board", "Committee", "Auditor", "Shareholder"]:
            return props.get("name", props.get("type", "")).lower().strip()
        else:
            # Fallback generico
            return " ".join(map(str, props.values())).lower().strip()

    def _find_best_match(
        self, new_node: Dict, existing_nodes: Dict
    ) -> Optional[Tuple[str, int]]:
        """
        Trova il miglior match per un nuovo nodo tra quelli esistenti usando fuzzy matching.
        Restituisce l'ID del nodo esistente e il punteggio di somiglianza se sopra la soglia.
        """
        new_node_str = self._get_node_comparison_string(new_node)
        if not new_node_str:
            return None

        best_match_id = None
        best_score = 0

        # Confronta solo con nodi dello stesso tipo (label)
        for existing_id, existing_node in existing_nodes.items():
            if existing_node["label"] == new_node["label"]:
                existing_node_str = self._get_node_comparison_string(existing_node)

                # Usiamo token_sort_ratio che è robusto all'ordine delle parole
                score = fuzz.token_sort_ratio(new_node_str, existing_node_str)

                if score > best_score:
                    best_score = score
                    best_match_id = existing_id

        if best_score >= self.similarity_threshold:
            return best_match_id, best_score

        return None

    def _find_best_match_by_id(
        self, new_node: Dict, existing_nodes: Dict
    ) -> Optional[Tuple[str, int]]:
        """
        Trova il miglior match per un nuovo nodo tra quelli esistenti usando fuzzy matching sugli ID.
        Restituisce l'ID del nodo esistente e il punteggio di somiglianza se sopra la soglia.
        """
        new_node_id = new_node["id"]
        best_match_id = None
        best_score = 0

        # Confronta solo con nodi dello stesso tipo (label) per evitare fusioni errate
        for existing_id, existing_node in existing_nodes.items():
            if existing_node["label"] == new_node["label"]:
                # Usiamo token_sort_ratio che è robusto all'ordine delle parole
                score = fuzz.token_sort_ratio(new_node_id, existing_id)
                if score > best_score:
                    best_score = score
                    best_match_id = existing_id

        if best_score >= self.similarity_threshold:
            return best_match_id, best_score

        return None

    def _update_properties(self, new_props: Dict, old_props: Dict) -> None:
        """
        Updates properties of an existing entity (node or edge).
        For string values, it keeps the longer one, assuming it's more complete.
        """
        for key, value in new_props.items():
            # Aggiorna solo se il nuovo valore non è nullo/vuoto
            if value is not None and value != "":
                if key not in old_props or old_props[key] == "":
                    old_props[key] = value
                elif isinstance(value, str) and isinstance(old_props.get(key), str):
                    # Se entrambi sono stringhe, preferisci la più lunga
                    if len(value) > len(old_props[key]):
                        old_props[key] = value
                else:
                    # Per altri tipi, sovrascrivi con il nuovo valore
                    old_props[key] = value

    def _collect_chunks_results(self, chunks_results: List[Dict]) -> Dict:
        """
        Collects and merges results from all chunks using fuzzy matching on node IDs.
        """
        final_result = {"nodes": {}, "edges": {}}
        id_map = {}  # Mappa da ID originali a ID finali (unificati)

        for res in chunks_results:
            result_data = res.get("result")
            if not result_data:
                continue

            # 1. Processa e unisci i nodi
            for node in result_data.nodes:
                node_dict = {
                    "id": node.id,
                    "label": node.label,
                    "properties": node.properties.copy(),
                }

                match = self._find_best_match_by_id(node_dict, final_result["nodes"])

                if match:
                    # Trovato un nodo simile, unisci le proprietà
                    existing_node_id = match[0]
                    self._update_properties(
                        node.properties,
                        final_result["nodes"][existing_node_id]["properties"],
                    )
                    # Mappa l'ID di questo nodo duplicato all'ID del nodo esistente
                    id_map[node.id] = existing_node_id
                else:
                    # Nuovo nodo, aggiungilo
                    final_result["nodes"][node.id] = node_dict
                    # Mappa il suo ID a se stesso
                    id_map[node.id] = node.id

        # 2. Processa gli archi usando la mappa degli ID
        for res in chunks_results:
            result_data = res.get("result")
            if not result_data:
                continue

            for edge in result_data.edges:
                # Traduci source e dest usando la mappa degli ID
                source_id = id_map.get(edge.source)
                dest_id = id_map.get(edge.dest)

                # Se un ID non è nella mappa (es. da un nodo scartato), salta l'arco
                if not source_id or not dest_id:
                    continue

                # Crea una chiave unica per l'arco per gestire i duplicati
                edge_key = (source_id, edge.type, dest_id)

                if edge_key in final_result["edges"]:
                    # Arco già esistente, aggiorna le proprietà
                    self._update_properties(
                        edge.properties, final_result["edges"][edge_key]["properties"]
                    )
                else:
                    # Nuovo arco, aggiungilo con gli ID corretti
                    final_result["edges"][edge_key] = {
                        "source": source_id,
                        "type": edge.type,
                        "dest": dest_id,
                        "properties": edge.properties.copy(),
                    }

        # Converti i dizionari di nodi e archi in liste per l'output finale
        final_result["nodes"] = list(final_result["nodes"].values())
        final_result["edges"] = list(final_result["edges"].values())
        return final_result

    def _validate_results(self, results: Dict) -> ReportResultsTemp:
        """
        Validates and cleans the final results using the ValidationAgent.
        """
        try:
            validated_results = self.validation_agent.validate_results(results)
            return validated_results
        except Exception as e:
            message = f"Error validating final results."
            raise WorkflowException(message) from e

    def _add_source_to_results(
        self, results: ReportResultsTemp, source_url: str
    ) -> None:
        """
        Adds the source URL to all nodes and edges in the results.
        """
        source_property = {"source": source_url}

        for node in results.nodes:
            if "source" not in node.properties:
                node.properties.update(source_property)

        for edge in results.edges:
            if "source" not in edge.properties:
                edge.properties.update(source_property)
