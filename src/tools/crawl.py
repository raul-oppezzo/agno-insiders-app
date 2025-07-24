import asyncio
import tempfile
import os
import requests
from typing import Any, Dict, List, Optional, Union

from agno.tools import Toolkit
from agno.utils.log import log_debug, log_warning

try:
    from crawl4ai import AsyncWebCrawler, CacheMode, BrowserConfig, CrawlerRunConfig
    from crawl4ai.content_filter_strategy import BM25ContentFilter, PruningContentFilter
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
except ImportError:
    raise ImportError(
        "`crawl4ai` not installed. Please install using `pip install crawl4ai`"
    )


class CrawlTools(Toolkit):
    """Toolkit for crawling web pages and extracting content using Crawl4ai."""

    def __init__(
        self,
        max_length: Optional[int] = 10000,
        timeout: int = 30,
        headless: bool = True,
        wait_until: str = "domcontentloaded",
        cache_mode: bool = False,
        check_robots_txt: bool = False,
        verbose: bool = False,
        remove_forms: bool = True,
        exclude_external_links: bool = True,
        exclude_social_media_links: bool = True,
        excluded_tags: Optional[list[str]] = [
            "script",
            "style",
            "nav",
            "header",
            "footer",
        ],
        use_pruning: bool = False,
        pruning_threshold: float = 0.48,
        bm25_threshold: float = 0.5,
        magic: bool = True,
        governance_mode: bool = False,
        **kwargs,
    ):
        super().__init__(name="crawl_tools", tools=[self.crawl], **kwargs)
        self.max_length = max_length
        self.timeout = timeout
        self.headless = headless
        self.wait_until = wait_until
        self.cache_mode = CacheMode.BYPASS if not cache_mode else CacheMode.DEFAULT
        self.check_robots_txt = check_robots_txt
        self.verbose = verbose
        self.remove_forms = remove_forms
        self.exclude_external_links = exclude_external_links
        self.exclude_social_media_links = exclude_social_media_links
        self.excluded_tags = excluded_tags or []
        self.use_pruning = use_pruning
        self.pruning_threshold = pruning_threshold
        self.bm25_threshold = bm25_threshold
        self.magic = magic
        self.governance_mode = governance_mode

    def _build_config(self, search_query: Optional[str] = None) -> Dict[str, Any]:
        """Build CrawlerRunConfig parameters from toolkit settings."""
        config_params = {
            "page_timeout": self.timeout * 1000,  # Convert to milliseconds
            "wait_until": self.wait_until,
            "cache_mode": self.cache_mode,
            "check_robots_txt": self.check_robots_txt,
            "remove_forms": self.remove_forms,
            "exclude_external_links": self.exclude_external_links,
            "exclude_social_media_links": self.exclude_social_media_links,
            "excluded_tags": self.excluded_tags,
            "magic": self.magic,
        }

        # Ensure excluded_tags is a list, not a tuple or nested structure
        if self.excluded_tags and not isinstance(self.excluded_tags, list):
            config_params["excluded_tags"] = list(self.excluded_tags)

        if self.use_pruning or search_query:
            if search_query:
                content_filter = BM25ContentFilter(
                    user_query=search_query, bm25_threshold=self.bm25_threshold
                )
                log_debug(f"Using BM25ContentFilter for query: {search_query}")
            else:
                content_filter = PruningContentFilter(
                    threshold=self.pruning_threshold,
                    threshold_type="fixed",
                    min_word_threshold=2,
                )
                log_debug("Using PruningContentFilter for general cleanup")

            config_params["markdown_generator"] = DefaultMarkdownGenerator(
                content_filter=content_filter
            )
            log_debug("Using DefaultMarkdownGenerator with content_filter")

        return config_params

    def crawl(
        self, url: Union[str, List[str]], search_query: Optional[str] = None
    ) -> Union[str, Dict[str, str]]:
        """
        Crawl URLs and extract their text content.

        Args:
            url: Single URL string or list of URLs to crawl
            search_query: Optional query string to filter content using BM25 algorithm

        Returns:
            The extracted text content from the URL(s)
        """
        if not url:
            return "Error: No URL provided"

        # Handle single URL
        if isinstance(url, str):
            return asyncio.run(self._async_crawl(url, search_query))

        # Handle list of URLs
        results = {}
        for single_url in url:
            results[single_url] = asyncio.run(
                self._async_crawl(single_url, search_query)
            )
        return results

    async def _async_crawl(self, url: str, search_query: Optional[str] = None) -> str:
        """Crawl a single URL and extract content."""

        try:
            browser_config = BrowserConfig(
                headless=self.headless,
                verbose=self.verbose,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                # Build configuration from parameters
                config_params = self._build_config(search_query)

                config = CrawlerRunConfig(**config_params)
                log_debug(f"Crawling URL: {url} with config: {config}")
                result = await crawler.arun(url=url, config=config)

                # Process the result
                if not result:
                    return "Error: No content found"

                log_debug(f"Result attributes: {dir(result)}")
                log_debug(f"Result success: {getattr(result, 'success', 'N/A')}")

                # Try to get markdown content
                content = ""
                if hasattr(result, "fit_markdown") and result.fit_markdown:
                    content = result.fit_markdown
                    log_debug("Using fit_markdown")
                elif hasattr(result, "markdown") and result.markdown:
                    if hasattr(result.markdown, "raw_markdown"):
                        content = result.markdown.raw_markdown
                        log_debug("Using markdown.raw_markdown")
                    else:
                        content = str(result.markdown)
                        log_debug("Using str(markdown)")
                else:
                    # Try to get any text content
                    if hasattr(result, "text"):
                        content = result.text
                        log_debug("Using text attribute")
                    elif hasattr(result, "html"):
                        log_warning("Only HTML available, no markdown extracted")
                        return "Error: Could not extract markdown from page"

                if not content:
                    log_warning(f"No content extracted. Result type: {type(result)}")
                    return "Error: No readable content extracted"

                log_debug(f"Extracted content length: {len(content)}")

                # Truncate if needed
                if self.max_length and len(content) > self.max_length:
                    content = content[: self.max_length] + "..."

                return content

        except Exception as e:
            log_warning(f"Exception during crawl: {str(e)}")
            error_msg = f"Crawl4AI Error: This page is not fully supported. Error Message: {str(e)} Possible reasons: 1. The page may have restrictions that prevent crawling. 2. The page might not be fully loaded. Suggestions: - Try calling the crawl function with these parameters: magic=True, - Set headless=False to visualize what's happening on the page. If the issue persists, please check the page's structure and any potential anti-crawling measures."
            return error_msg
