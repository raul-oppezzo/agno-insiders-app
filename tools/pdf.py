import asyncio
import os
import tempfile
import threading
from typing import Any, Dict
from urllib.parse import urlparse
import requests
from io import BytesIO

from agno.tools import Toolkit
from agno.utils.log import logger
from agno.utils.log import log_debug, log_warning
import urllib3

from playwright.async_api import async_playwright

try:
    import PyPDF2
except ImportError:
    raise ImportError(
        "`PyPDF2` not installed. Please install it with `pip install PyPDF2`."
    )


class PDFTools(Toolkit):
    """Toolkit for handling PDF files."""

    def __init__(self, max_length: int = 10000, **kwargs):
        self.max_length = max_length
        super().__init__(name="pdf_tools", tools=[self.get_pdf_content], **kwargs)

    def get_pdf_content(self, pdf_path: str) -> str:
        try:
            asyncio.get_running_loop()
            # running loop -> run in background thread with its own loop
            return self._run_coro_in_thread(self._download_report(pdf_path))
        except RuntimeError:
            # no running loop -> safe to use asyncio.run
            return asyncio.run(self._download_report(pdf_path))
        
    def _run_coro_in_thread(self, coro: asyncio.coroutines) -> Any:
        """Run coroutine in a separate thread with its own event loop and return the result."""
        result_container: Dict[str, Any] = {}
        exc_container: Dict[str, BaseException] = {}

        def _runner():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result_container["result"] = loop.run_until_complete(coro)
            except BaseException as e:
                exc_container["exc"] = e
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()

        if "exc" in exc_container:
            raise exc_container["exc"]
        return result_container.get("result")

    async def _download_report(self, report_url: str) -> str:
        """
        Download the report using Playwright Async API and save to a temporary file.
        Returns the temp file path.
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
                    logger.warning(f"context.request.get failed: {e}")
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
                        return "URL does not point to a PDF file."

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
                                    return "URL does not point to a PDF file."
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
                                return "URL does not point to a PDF file."
                        except Exception as e:
                            return "Unable to fetch report after retries."

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
            return "Unable to download report."

        if not tmp_file_path:
            return "Unable to download report."
        
        try:
            if tmp_file_path.endswith(".pdf"):
                pdf_file = BytesIO(response.content)
                pdf_reader = PyPDF2.PdfReader(pdf_file)

                text = "### PDF Content ###\n"
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"

                if self.max_length and len(text) > self.max_length:
                    text = text[: self.max_length] + "..."

                return text
        except Exception as e:
            return "Error processing PDF."
        finally:
            try:
                if tmp_file_path and os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
            except Exception:
                pass
        
        return "No content extracted."


################# Unused #######################

    def get_report_pages(self, start: int, end: int) -> str:
        pages_text = []
        for el in self.elements:
            # Access metadata as an attribute, not a dictionary key
            if hasattr(el, "metadata") and el.metadata:
                el_page = getattr(el.metadata, "page_number", None)
                if el_page and el_page >= start and el_page <= end:
                    # Access text as an attribute
                    if hasattr(el, "text") and el.text:
                        pages_text.append(el.text)

        return "\n".join(pages_text)

    def extract_text_from_url(self, pdf_url: str) -> str:
        """Extract text from a PDF file located at a given URL."""

        log_debug(f"Extracting text from PDF at URL: {pdf_url}")

        try:
            response = requests.get(pdf_url)
            response.raise_for_status()

            # Process with PyPDF2
            pdf_file = BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            text = "### PDF Content ###\n"
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"

            return text.strip()
        except requests.RequestException as e:
            log_warning(f"Failed to fetch PDF from URL: {pdf_url}. Error: {e}")
            return f"Failed to fetch PDF from URL: {pdf_url}."
        except Exception as e:
            log_warning(f"Error processing PDF: {e}")
            return "Error processing PDF."
