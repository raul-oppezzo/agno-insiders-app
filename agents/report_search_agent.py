import os
from typing import Optional

from agno.agent import Agent, RunResponse
from agno.models.google import Gemini
from agno.tools.googlesearch import GoogleSearchTools
from agno.tools.reasoning import ReasoningTools
from agno.utils.log import logger

from tools.crawl import CrawlTools

from models.report_url import ReportURL
from prompts.report_search_agent_prompt import (
    DESCRIPTION,
    ADDITIONAL_CONTEXT,
    INSTRUCTIONS,
)

DEBUG = os.getenv("DEBUG", "False").lower() == "true"
EXPONENTIAL_BACKOFF = os.getenv("BACKOFF", "True").lower() == "true"
RETRIES = int(os.getenv("RETRIES", "3"))


class ReportSearchAgent:
    """An agent to search for corporate governance report on the web."""

    def __init__(self):
        self.agent = Agent(
            name="ReportSearchAgent",
            model=Gemini(
                id="gemini-2.5-flash",
                temperature=0.1,
                top_p=0.95,
            ),
            tools=[
                GoogleSearchTools(cache_results=True),
                CrawlTools(max_length=25000, cache_results=True),
                ReasoningTools(add_instructions=True),
            ],
            description=DESCRIPTION,
            additional_context=ADDITIONAL_CONTEXT,
            instructions=INSTRUCTIONS,
            show_tool_calls=True,
            tool_call_limit=15,
            use_json_mode=True,
            response_model=ReportURL,
            debug_mode=DEBUG,
            exponential_backoff=EXPONENTIAL_BACKOFF,
            retries=RETRIES,
            add_datetime_to_instructions=True,  # to ensure the agent uses the current date and time in its reasoning
        )

    def search_report(self, company_name: str) -> ReportURL:
        """
        Search for the latest corporate governance report of a company.

        Args:
            company_name (str): The name of the company to search for.

        Returns:
            ReportURL: The URL of the corporate governance report.
        """
        try:
            logger.info(
                f"Searching for the corporate governance report of '{company_name}'..."
            )

            response: RunResponse = self.agent.run(
                f"Please, search the URL of the latest corporate governance report of company '{company_name}'."
            )

            if response is None or response.content is None:
                logger.error(f"No valid response received from {self.agent.name}.")
                raise RuntimeError(
                    f"No response or empty content received from {self.agent.name}."
                )

            if not isinstance(response.content, ReportURL):
                logger.error(f"Unexpected response type: {type(response.content)}.")
                raise RuntimeError(f"Expected ReportURL, got {type(response.content)}.")

            logger.info(f"Search completed successfully.")

            return response.content
        except Exception as e:
            logger.error(f"Error in {self.agent.name} during report search: {str(e)}")
            raise RuntimeError(
                f"Error in {self.agent.name} during report search: {str(e)}"
            ) from e
