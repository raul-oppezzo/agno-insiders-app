import os
from typing import Iterator

from agno.agent import Agent, RunResponse
from agno.models.google import Gemini
from agno.tools.googlesearch import GoogleSearchTools
from agno.tools.reasoning import ReasoningTools
from agno.utils.log import logger
from agno.utils.pprint import pprint_run_response

from tools.crawl import CrawlTools

from models.report_url import ReportURL
from prompts.report_search_agent_prompt import (
    DESCRIPTION,
    ADDITIONAL_CONTEXT,
    INSTRUCTIONS,
)

DEBUG = os.getenv("DEBUG", "False").lower() == "true"


class ReportSearchAgent:
    """An agent to search for corporate governance report on the web."""

    def __init__(self):
        self.agent = Agent(
            name="ReportSearchAgent",
            model=Gemini(
                id="gemini-2.5-flash",
                temperature=0.0,
                top_p=0.9,
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
            stream_intermediate_steps=True,
            tool_call_limit=25,
            use_json_mode=True,
            response_model=ReportURL,
            debug_mode=DEBUG,
            exponential_backoff=True,
            retries=2,
            delay_between_retries=30,  # Timeout of 30 seconds
            add_datetime_to_instructions=True,  # to ensure the agent uses the current date and time in its reasoning
        )

    def search_report(self, company_name: str) -> ReportURL:
        """
        Runs the agent to search for the latest corporate governance report of a company.

        Args:
            company_name (str): The name of the company to search for.

        Returns:
            ReportURL: The URL of the corporate governance report.
        """

        prompt = f"Please, search the URL of the latest corporate governance report of company '{company_name}'."

        try:
            response: Iterator[RunResponse] = self.agent.run(prompt, stream=False)
        except Exception as e:
            logger.error(f"Error in {self.agent.name}.")
            raise e

        if response.content is None:
            raise ValueError(f"Missing response content.")

        if not isinstance(response.content, ReportURL):
            raise TypeError(f"Expected ReportURL, got {type(response.content)}.")

        return response.content
