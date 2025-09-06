import os
import re
import tempfile
import time
import asyncio
from datetime import datetime

from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse

from agno.agent import Agent
from agno.workflow import RunResponse, Workflow
from agno.utils.log import logger
import requests
import urllib3

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

from models.report_results import ReportResults

from thefuzz import fuzz
from playwright.async_api import async_playwright


class InsidersWorkflow(Workflow):
    """
    A multi agent workflow designed to search and ingest corporate governance report data into a knowledge graph.
    """

    def __init__(self):
        super().__init__()
        self.max_characters = 55000  # Max characters per chunk
        self.overlap = 100  # Overlap between chunks
        self.max_concurrent = 5  # Max concurrent chunk analyses
        self.semaphore = asyncio.Semaphore(
            self.max_concurrent
        )  # Semaphore for limiting concurrency during chunk analysis
        self.report_search_agent: Agent = (
            ReportSearchAgent()
        )  # Agent to search for report URL
        self.report_analyze_agent: Agent = (
            ReportAnalyzeAgent()
        )  # Agent to analyze report chunks
        self.validation_agent: Agent = (
            ValidationAgent()
        )  # Agent to validate final results
        self.db = self._get_db_driver()  # Manages database connections and interactions

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

    def run(self, company_name: str, report_url: str) -> RunResponse:
        """
        Run the workflow for a target company.

        Args:
            company_name (str): The name of the target company.
            report_url (str): Optional direct URL to the corporate governance report in PDF format.

        Returns:
            RunResponse: The response of the workflow containing the summarized results or error message.
        """

        return asyncio.run(self._run_async(company_name, report_url))

    async def _run_async(self, company_name: str, report_url: str) -> RunResponse:
        """
        Asynchronous run method to handle the workflow steps:
        1. Search for the corporate governance report URL.
        2. If URL found, partition the report into elements.
        3. Chunk the elements.
        4. Analyze each chunk concurrently with a semaphore to limit concurrency.
        5. Summarize the results from all chunks.

        Args:
            company_name (str): The name of the target company.
            report_url (str): Optional direct URL to the corporate governance report in PDF format.

        Returns:
            RunResponse: The response of the workflow.
        """

        logger.info(f"Searching report for '{company_name}'...")

        report_url = report_url or self._get_report_url(company_name)
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
            return RunResponse(content="Workflow interrupted.")

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

        merged_results = self._collect_chunks_results(success_chunks)

        self._print_results_summary(ReportResults(**merged_results))

        logger.info(
            f"Merged results from chunks. Nodes: {len(merged_results['nodes'])}, Edges: {len(merged_results['edges'])}"
        )

        logger.info(f"Validating final results...")
        final_results: ReportResults = self._validate_results(merged_results)

        logger.info(
            f"Final results validated. Nodes: {len(final_results.nodes)}, Edges: {len(final_results.edges)}"
        )

        logger.info(f"Final results summary:")
        self._print_results_summary(final_results)

        self._add_source_to_results(final_results, report_url)

        answer = input(f"Do you want to save the results to the database? [Y/n] ")
        if answer.lower() in ["y", "yes"]:
            self.db.save_report_results(final_results)
            self.db.close()
            logger.info(f"Results saved to the database.")

        answer = input(f"Do you want to save the results locally? [Y/n] ")
        if answer.lower() in ["y", "yes"]:
            path = self._save_results_locally(final_results, company_name)
            logger.info(f"Results saved to {path}.")

        return RunResponse(content="Workflow completed successfully.")

    def _print_results_summary(self, results: ReportResults) -> None:
        """
        Prints a summary of the results.

        Args:
            results (ReportResults): The results to summarize.

        Returns:
            None
        """
        nodes = sorted(results.nodes, key=lambda n: n.label)
        edges = sorted(results.edges, key=lambda e: e.type)

        def print_properties(props: Dict) -> str:
            return ", ".join(f"{k}: {v}" for k, v in props.items())

        print(f"\nNodes: {len(nodes)}")
        for n in nodes:
            print(f"ID: {n.id} label: {n.label} {print_properties(n.properties)}")

        print(f"\nEdges: {len(edges)}")
        for e in edges:
            print(f"{e.source} -[{e.type}]-> {e.dest} {print_properties(e.properties)}")

    def _get_report_url(self, company_name: str) -> str:
        """
        Calls the ReportSearchAgent to get the report URL for the given company name.

        Args:
            company_name (str): The name of the target company.

        Returns:
            str: The URL of the corporate governance report.
        """
        try:
            report: Report = self.report_search_agent.search_report(company_name)
            return report.url
        except Exception as e:
            message = f"Unable to find governance report for '{company_name}'."
            raise WorkflowException(message) from e

    def _save_results_locally(self, results: ReportResults, company_name: str):
        """
        Saves the results to a local JSON file.

        Args:
            results (ReportResults): The results to save.
            company_name (str): The name of the company.

        Returns:
            str: The path to the saved file.
        """
        while not company_name:
            company_name = input("Enter company name for filename: ").strip()

        os.makedirs("results/v4", exist_ok=True)
        filename = f"{company_name.replace(' ', '_').lower()}_insiders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join("results/v4", filename)
        with open(filepath, "w") as f:
            f.write(results.model_dump_json(indent=2))
        return filepath

    async def _download_report(self, report_url: str) -> str:
        """
        Download the report using Playwright Async API and save to a temporary file.

        Args:
            report_url (str): The URL of the report to download.

        Returns:
            str: The path to the temporary file containing the downloaded report.
        """
        tmp_file_path = None
        origin = f"{urlparse(report_url).scheme}://{urlparse(report_url).netloc}"

        # suppress insecure request warnings for fallback fetch
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--ignore-ssl-errors", "--ignore-certificate-errors"],
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    ignore_https_errors=True,
                )
                page = await context.new_page()

                # Try a navigation to detect WAF/challenge (don't rely on it for PDF body)
                resp = None
                try:
                    resp = await page.goto(
                        report_url, wait_until="networkidle", timeout=30000
                    )
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
                    if (
                        "_Incapsula_Resource" in html_str
                        or "visid_incap" in html_str
                        or "captcha" in html_str.lower()
                    ):
                        return True
                    if resp is not None:
                        status = getattr(resp, "status", None)
                        if status in (403, 429):
                            return True
                        ctype = (resp.headers.get("content-type") or "").lower()
                        if "text/html" in ctype and (
                            "_Incapsula_Resource" in html_str
                            or "Request unsuccessful" in html_str
                        ):
                            return True
                    return False

                if _is_challenge(resp, html):
                    logger.info(
                        f"WAF/challenge detected for {report_url}, doing origin pre-flight {origin}"
                    )
                    try:
                        await page.goto(origin, wait_until="networkidle", timeout=45000)
                        for pth in ["/", "/en", "/it"]:
                            try:
                                await page.goto(
                                    origin.rstrip("/") + pth,
                                    wait_until="networkidle",
                                    timeout=20000,
                                )
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(f"Pre-flight origin visit failed: {e}")

                # Prefer context.request.get to fetch the raw resource (works for PDFs)
                response = None
                try:
                    response = await context.request.get(report_url, timeout=60000)
                    logger.info(
                        f"context.request.get response status: {getattr(response, 'status', None)}"
                    )
                except Exception as e:
                    logger.debug(f"context.request.get failed: {e}")
                    response = None

                data = None
                suffix = ""
                if response is not None and 200 <= response.status < 300:
                    ctype = (response.headers.get("content-type") or "").lower()
                    if "application/pdf" in ctype or report_url.lower().endswith(
                        ".pdf"
                    ):
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
                    # If Playwright failed and the failure looks like a cert issue or context.request failed,
                    # try a simple requests.get fallback (disable SSL verification).
                    tried_requests_fallback = False
                    if response is None:
                        err_msg = ""
                        # If we have debug log of earlier exception, check for certificate text in it
                        # fall back unconditionally when context.request.get didn't succeed
                        try:
                            logger.info(
                                "Attempting requests fallback with verify=False due to Playwright request failure."
                            )
                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                            }
                            r = requests.get(
                                report_url, headers=headers, timeout=60, verify=False
                            )
                            tried_requests_fallback = True
                            if 200 <= r.status_code < 300:
                                ctype = (r.headers.get("content-type") or "").lower()
                                if (
                                    "application/pdf" in ctype
                                    or report_url.lower().endswith(".pdf")
                                ):
                                    data = r.content
                                    suffix = ".pdf"
                                elif (
                                    "text/html" in ctype
                                    or report_url.lower().endswith(".html")
                                ):
                                    data = r.text.encode("utf-8")
                                    suffix = ".html"
                                else:
                                    data = r.content
                            else:
                                logger.debug(
                                    f"requests fallback returned status {r.status_code}"
                                )
                        except Exception as e:
                            logger.debug(f"requests fallback failed: {e}")
                            tried_requests_fallback = False

                    if (data is None) and (not tried_requests_fallback):
                        # Last-resort fallback: try a lighter navigation and grab page content
                        try:
                            resp2 = await page.goto(
                                report_url, wait_until="domcontentloaded", timeout=30000
                            )
                            # try to detect pdf by headers if present
                            ctype = ""
                            if resp2 is not None:
                                ctype = (
                                    resp2.headers.get("content-type") or ""
                                ).lower()
                            if resp2 is not None and "application/pdf" in ctype:
                                data = await resp2.body()
                                suffix = ".pdf"
                            else:
                                html2 = await page.content()
                                data = html2.encode("utf-8")
                                suffix = ".html"
                        except Exception as e:
                            message = f"Unable to fetch report after retries: {e}"
                            raise WorkflowException(message) from e

                # write to temp file
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=suffix
                ) as tmp_file:
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
            raise WorkflowException(
                f"Unable to download report: no file created for {report_url}"
            )
        return tmp_file_path

    def _partition_report(self, tmp_file_path: str) -> List:
        """
        Partitions the report into elements using unstructured library.

        Args:
            tmp_file_path (str): Path to the temporary file containing the report.

        Returns:
            List: List of partitioned elements.
        """
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
        """
        Cleans the elements by removing unwanted characters and grouping broken paragraphs.

        Args:
            elements (List): List of elements to clean.

        Returns:
            None
        """
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
        """
        Chunks the elements into manageable pieces based on max_characters and overlap.

        Args:
            elements (List): List of elements to chunk.

        Returns:
            List: List of chunks.
        """
        try:
            chunks = chunk_elements(
                elements, max_characters=self.max_characters, overlap=self.overlap
            )
            return chunks
        except Exception as e:
            message = f"Error chunking report elements."
            raise WorkflowException(message) from e

    async def _process_chunks(self, chunks) -> List[Dict]:
        """
        Processes all chunks concurrently with a semaphore to limit concurrency.

        Args:
            chunks (List): List of chunks to process.

        Returns:
            List[Dict]: List of results from processing each chunk.
        """
        tasks = [
            self._analyze_chunk_with_semaphore(index, chunk)
            for index, chunk in enumerate(chunks)
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _analyze_chunk_with_semaphore(self, index: int, chunk) -> Dict:
        """
        Analyzes a single chunk with concurrency control using a semaphore.

        Args:
            index (int): The index of the chunk.
            chunk: The chunk to analyze.

        Returns:
            Dict: The result of the analysis or error information.
        """
        async with self.semaphore:
            try:
                res = await self.report_analyze_agent.analyze_chunk_async(
                    index, chunk.text
                )
                print(f"""\n{'***'} Chunk:{index} {'***'}\n{res}""")

                return {"chunk_index": index, "result": res}
            except KeyboardInterrupt as e:
                logger.error("Process interrupted by user.")
                raise e
            except Exception as e:
                logger.error(f"Errpr processing chunk {index}: {str(e)}")
                return {"chunk_index": index, "error": str(e)}

    def _get_node_comparison_string(self, node: Dict) -> str:
        """
        Creates a representative string for a node for comparison.

        Args:
            node (Dict): The node to create the comparison string for.

        Returns:
            str: The comparison string.
        """
        props = node.get("properties", {}) or {}
        label = (node.get("label", "")).lower() or ""

        if label in ["person", "company", "committee", "auditor"]:
            return self._normalize_str(props.get("name", ""))
        elif label == "board":
            return self._normalize_str(props.get("type", ""))
        else:
            # Generic fallback
            return self._normalize_str(" ".join(map(str, props.values())))

    def _find_match(self, new_node: Dict, existing_nodes: List[Dict]) -> Optional[str]:
        """
        Finds the best match for a new node among existing ones using fuzzy matching on IDs.

        Args:
            node_id (Dict): The new node to match.
            existing_nodes (List[Dict]): Existing nodes to compare against.

        Returns:
            Optional[str]: The ID of the existing node if similarity score above threshold, else None.
        """
        best_match_id = None
        best_score = 0

        new_id = new_node.get("id", "") or ""
        new_label = new_node.get("label", "") or ""
        new_norm = self._get_node_comparison_string(new_node) or ""
        new_id_norm = self._normalize_str(new_id)

        # Compare only with nodes of the same type (label)
        for existing_id, existing_node in existing_nodes.items():
            if (existing_node.get("label", "") or "") != new_label:
                continue

            existing_norm = self._get_node_comparison_string(existing_node)
            existing_id_norm = self._normalize_str(existing_id)

            if existing_norm and new_norm and new_norm == existing_norm:
                return existing_id

            id_score = fuzz.token_sort_ratio(new_id_norm, existing_id_norm)
            norm_score = (
                fuzz.token_set_ratio(new_norm, existing_norm)
                if existing_norm and new_norm
                else 0
            )

            combined = int(0.7 * id_score + 0.3 * norm_score)

            if combined > best_score:
                best_score = combined
                best_match_id = existing_id

        if best_score >= 80:
            return best_match_id

        return None

    def _update_properties(self, old: Dict, new: Dict) -> None:
        """
        Updates properties of an existing entity (node or edge). Keeps the longer one, assuming it's more complete.

        Args:
            old (Dict): old entity.
            new (Dict): new entity.

        Returns:
            None
        """
        new_props = new["properties"]
        old_props = old["properties"]

        for key, value in new_props.items():
            # Update only if the new value is not None or empty
            if value is not None and value != "":
                if key not in old_props or old_props[key] == "":
                    old_props[key] = value
                elif value == old_props[key]:
                    continue
                elif isinstance(value, str) and isinstance(old_props.get(key), str):
                    # Keep the longer string, assuming it's more complete
                    if len(value) > len(old_props[key]):
                        old_props[key] = value
                else:
                    # Default to replacing the old value
                    old_props[key] = value

    def _collect_chunks_results(self, chunks_results: List[Dict]) -> Dict:
        """
        Try to merge results from all chunks using fuzzy matching on node IDs.

        Args:
            chunks_results (List[Dict]): List of results from each chunk.

        Returns:
            Dict: Potentially merged results containing unique nodes and edges.
        """
        final_nodes = {}
        final_edges = {}
        id_map = {}  # Maps matched IDs to final IDs

        for res in chunks_results:
            result_data = res.get("result")  # ReportResults object
            if not result_data:
                continue

            for node in result_data.nodes:
                node_dict = {
                    "id": node.id,
                    "label": node.label,
                    "properties": node.properties.copy(),
                }
                match_id = self._find_match(node_dict, final_nodes)
                if match_id:
                    self._update_properties(
                        final_nodes[match_id],
                        node_dict,
                    )
                    canonical = match_id
                    logger.info(f"Merging node {node.id} -> {canonical}")
                else:
                    canonical = node.id
                    final_nodes[canonical] = node_dict
                    logger.info(f"Adding new node {canonical}")

                # Keep track of ID mapping for edges analysis
                id_map[node.id] = canonical

            for edge in result_data.edges:
                src = id_map.get(edge.source, edge.source)
                dst = id_map.get(edge.dest, edge.dest)
                edge_key = f"{src}_{edge.type}_{dst}"
                edge_obj = {
                    "source": src,
                    "type": edge.type,
                    "dest": dst,
                    "properties": edge.properties.copy(),
                }

                if edge_key in final_edges:
                    existing = final_edges[edge_key]
                    
                    # Skip exact duplicates
                    if edge_obj["properties"] == existing["properties"]:
                        logger.info(f"Duplicate exact edge {edge_key}, skipping.")
                        continue
                    
                    if edge_obj["properties"] == {}:
                        logger.info(
                            f"Duplicate empty edge properties for {edge_key}, skipping."
                        )
                        continue
                    if existing["properties"] == {}:
                        final_edges[edge_key] = edge_obj
                        logger.info(f"Updated empty edge properties for {edge_key}.")
                        continue

                    temp = set(edge_obj["properties"].keys()).intersection(
                        set(existing["properties"].keys())
                    )
                    temp.discard("from")
                    temp.discard("to")
                    
                    # If no overlapping properties, merge
                    if not temp or len(temp) == 0:
                        logger.info(
                            f"Duplicate edge with no overlapping properties for {edge_key}, merging."
                        )
                        self._update_properties(existing, edge_obj)
                        continue

                    # If overlapping properties, check similarity
                    if self._has_similar_properties(
                        edge_obj["properties"], existing["properties"]
                    ):
                        self._update_properties(existing, edge_obj)
                        logger.info(f"Updated edge properties for {edge_key}")
                    else:
                        suffix = 1
                        new_key = f"{edge_key}_{suffix}"
                        while new_key in final_edges:
                            suffix += 1
                            new_key = f"{edge_key}_{suffix}"
                        final_edges[new_key] = edge_obj
                        logger.info(f"Keeping distinct edge as {new_key}")
                else:
                    final_edges[edge_key] = edge_obj

        return {
            "nodes": list(final_nodes.values()),
            "edges": list(final_edges.values()),
        }
    
    def _normalize_str(self, v: Optional[str]) -> str:
        """
        Normalizza una stringa per il confronto:
        - None -> ""
        - strip, lower
        - rimuove punteggiatura e whitespace multipli
        """
        if v is None:
            return ""
        s = str(v).strip().lower()
        # rimuovi punteggiatura comune mantenendo lettere/numeri/spazi
        s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
        # collassa più spazi in uno
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _has_similar_properties(self, props1: Dict, props2: Dict) -> bool:
        """
        Checks if two sets of properties are similar enough to consider the edges as duplicates.

        Args:
            props1 (Dict): First set of properties.
            props2 (Dict): Second set of properties.

        Returns:
            bool: True if properties are similar, False otherwise.
        """
        if not props1 or not props2:
            return False

        # Consider only keys present in either (but require overlap)
        common_keys = set(props1.keys()).intersection(set(props2.keys()))
        # Ignore date fields for similarity
        common_keys.discard("from")
        common_keys.discard("to")
        if not common_keys or len(common_keys) == 0:
            return False

        match_count = 0
        for key in common_keys:
            v1 = props1.get(key)
            v2 = props2.get(key)
            if v1 is None or v2 is None:
                continue

            s1 = self._normalize_str(v1)
            s2 = self._normalize_str(v2)
            if s1 == s2:
                match_count += 1
                continue

            s1_clean = s1.replace("independent", "").replace("non-executive", "").replace("executive", "").replace("non-independent", "")
            s2_clean = s2.replace("independent", "").replace("non-executive", "").replace("executive", "").replace("non-independent", "")
            if s1_clean == s2_clean:
                match_count += 1
                continue

            score = fuzz.token_set_ratio(s1, s2)
            if score >= 70:
                match_count += 1

        similarity_ratio = match_count / len(common_keys)
        return similarity_ratio >= 0.5

    def _validate_results(self, results: Dict) -> ReportResults:
        """
        Validates and cleans the final results using the ValidationAgent.

        Args:
            results (Dict): The results to validate.

        Returns:
            ReportResults: The validated and cleaned results.
        """
        retries = 3
        for attempt in range(retries):
            try:
                validated_results = self.validation_agent.validate_results(results)
                return validated_results
            except Exception as e:
                if attempt < retries - 1:
                    message = f"Error validating final results (attempt {attempt + 1}): {str(e)}. Retrying..."
                    logger.warning(message)
                else:
                    message = "Max retries reached. Unable to validate final results."
                    raise WorkflowException(message) from e

    def _add_source_to_results(self, results: ReportResults, source_url: str) -> None:
        """
        Adds the source URL to all nodes and edges in the results.

        Args:
            results (ReportResults): The results to update.
            source_url (str): The source URL to add.

        Returns:
            None
        """
        source_property = {"source": source_url}

        for node in results.nodes:
            if "source" not in node.properties:
                node.properties.update(source_property)

        for edge in results.edges:
            if "source" not in edge.properties:
                edge.properties.update(source_property)


############ Unused ###############


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

    for res in chunks_results:
        result_data = res.get("result")  # ReportResults object
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

            if edge_key in final_result["edges"] or (
                edge_key == "HOLDS_POSITION"
                and self._has_similar_properties(
                    edge.properties, final_result["edges"][edge_key]["properties"]
                )
            ):
                logger.info(f"Duplicate edge detected: {edge_key}, merging properties.")
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


def _summarize_results(self, chunks_results: List[str]) -> ReportResults:
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
        return (
            f"{props.get('firstName', '')} {props.get('lastName', '')}".lower().strip()
        )
    elif label == "Company":
        return props.get("name", "").lower().strip()
    elif label in ["Board", "Committee", "Auditor", "Shareholder"]:
        return props.get("name", props.get("type", "")).lower().strip()
    else:
        # Fallback generico
        return " ".join(map(str, props.values())).lower().strip()
