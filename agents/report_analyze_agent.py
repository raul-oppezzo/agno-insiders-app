import os

from agno.agent import Agent, RunResponse
from agno.models.google import Gemini
from agno.tools.reasoning import ReasoningTools
from agno.utils.log import logger

from tools.pdf import PDFTools

from models.report_results import ReportResults
from prompts.report_analyze_agent_prompt import (
    DESCRIPTION,
    ADDITIONAL_CONTEXT,
    INSTRUCTIONS,
)


DEBUG = os.getenv("DEBUG", "False").lower() == "true"
EXPONENTIAL_BACKOFF = os.getenv("BACKOFF", "True").lower() == "true"
RETRIES = int(os.getenv("RETRIES", "3"))


class ReportAnalyzeAgent:

    def __init__(self):
        self.agent = Agent(
            name="ReportAnalyzeAgent",
            model=Gemini(
                id="gemini-2.5-flash",
                temperature=0.1,
                top_p=0.95,
            ),
            tools=[
                PDFTools(cache_results=True),
                ReasoningTools(add_instructions=True),
            ],
            description=DESCRIPTION,
            additional_context=ADDITIONAL_CONTEXT,
            instructions=INSTRUCTIONS,
            show_tool_calls=True,
            tool_call_limit=15,
            use_json_mode=True,
            response_model=ReportResults,
            debug_mode=DEBUG,
            exponential_backoff=EXPONENTIAL_BACKOFF,
            retries=RETRIES,
        )

    def analyze_report(self, report_url: str) -> ReportResults:
        """
        Search for insiders in a corporate governance report.

        Args:
            report_url (str): The URL of the corporate governance report.

        Returns:
            ReportResults: The results of the analysis containing company, governing bodies, and insiders.
        """

        try:
            logger.info(f"Analyzing report at {report_url}...")

            response: RunResponse = self.agent.run(
                f"Please, analyze the corporate governance report at {report_url}."
            )

            if response is None or response.content is None:
                logger.error(f"No valid response received from {self.agent.name}.")
                raise RuntimeError(
                    f"No response or empty content received from {self.agent.name}."
                )

            if not isinstance(response.content, ReportResults):
                logger.error(f"Unexpected response type: {type(response.content)}.")
                raise RuntimeError(
                    f"Expected ReportResults, got {type(response.content)}."
                )

            logger.info(f"Successfully analyzed report at {report_url}.")
            
            return response.content
        except Exception as e:
            logger.error(f"Error in {self.agent.name} during report analysis: {str(e)}")
            raise RuntimeError(
                f"Error in {self.agent.name} during report analysis: {str(e)}"
            ) from e
