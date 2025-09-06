from agno.agent import Agent, RunResponse
from agno.models.google import Gemini
from agno.tools import tool
from agno.tools.googlesearch import GoogleSearchTools
from agno.tools.reasoning import ReasoningTools

from exceptions.exceptions import AgentException
from tools.crawl import CrawlTools

from models.report import Report
from prompts.report_search_agent_prompt import (
    DESCRIPTION,
    INSTRUCTIONS,
)


@tool(name="user_confirmation_tool")
def confirmation_tool(report_url: str) -> str:
    """
    A tool to ask the user for confirmation. Use it to ask the user if the found report is correct.

    Args:
        report_url (str): The URL of the report to confirm.

    Returns:
        str: The user's confirmation response.
    """
    confirmation = input(f"Is this report URL correct? {report_url} (yes/no): ")
    return confirmation.strip().lower()


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
                GoogleSearchTools(fixed_max_results=3, cache_results=False),
                CrawlTools(max_length=50000, cache_results=False),
                confirmation_tool,
                ReasoningTools(add_instructions=True),
            ],
            description=DESCRIPTION,
            instructions=INSTRUCTIONS,
            tool_call_limit=25,
            use_json_mode=True,
            response_model=Report,
            debug_mode=True,
            exponential_backoff=True,
            retries=3,
            delay_between_retries=30,  # Timeout of 30 seconds
            add_datetime_to_instructions=True,  # Ensure the agent uses the current date and time in its reasoning
        )

    def search_report(self, company_name: str) -> Report:
        """
        Runs the agent to search for the latest corporate governance report of a company.

        Args:
            company_name (str): The name of the company to search for.

        Returns:
            Report: The the corporate governance report object, containing the report URL.
        """

        prompt = f"Please, search the URL of the latest corporate governance report of company '{company_name}'."

        try:
            response: RunResponse = self.agent.run(prompt, stream=False)
        except Exception as e:
            message = f"Error in {self.agent.name}."
            raise AgentException(message) from e

        if response.content is None:
            raise AgentException(f"Missing response content.")

        if not isinstance(response.content, Report):
            raise AgentException(f"Expected Report, got {type(response.content)}.")

        return response.content
