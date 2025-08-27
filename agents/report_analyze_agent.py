import os
from typing import Iterator

from agno.agent import Agent, RunResponse
from agno.models.google import Gemini
from agno.utils.log import logger

from agno.tools.reasoning import ReasoningTools

from models.report_results import ReportResultsTemp, ReportResults
from prompts.report_analyze_agent_prompt import (
    DESCRIPTION_TEMP,
    ADDITIONAL_CONTEXT_TEMP,
    INSTRUCTIONS_TEMP,
)
from tools.pdf import PDFTools

DEBUG = os.getenv("DEBUG", "False").lower() == "true"


class ReportAnalyzeAgent:

    def __init__(self):
        self.agent = Agent(
            name="ReportAnalyzeAgent",
            model=Gemini(
                id="gemini-2.5-flash",
                temperature=0.0,
            ),
            # tools=[ReasoningTools(add_instructions=True)],
            description=DESCRIPTION_TEMP,
            additional_context=ADDITIONAL_CONTEXT_TEMP,
            instructions=INSTRUCTIONS_TEMP,
            use_json_mode=True,
            response_model=ReportResultsTemp,
            debug_mode=DEBUG,
            exponential_backoff=True,
            retries=2,
            delay_between_retries=30,  # Timeout of 30 seconds
        )

    async def analyze_chunk_async(self, chunk_text: str) -> ReportResults:
        """
        Search for the insiders and governance data in the given chunk

        Args:
            chunk(object): an object containing a text field.

        Returns
            ReportResults: The results of the analysis.
        """

        chunk_prompt = f""" 
            Please analyze this chunk of the corporate governance report:
            
            **CHUNK**:
            \"\"\"
            {chunk_text}
            \"\"\"
            
            **OUTPUT**:
            """

        try:
            response = await self.agent.arun(chunk_prompt, stream=False)
        except Exception as e:
            logger.error(f"Error in {self.agent.name}.")
            raise e

        if response.content is None:
            raise ValueError(f"Missing response content.")

        if not isinstance(response.content, ReportResultsTemp):
            raise TypeError(f"Expected ReportResults, got {type(response.content)}.")

        return response.content

    def analyze_report(self, report_url: str = "") -> ReportResultsTemp:
        """
        Search for insiders in a corporate governance report.

        Args:
            report_url (str): The URL of the corporate governance report.

        Returns:
            ReportResults: The results of the analysis containing company, governing bodies, and insiders.
        """

        prompt = (
            f"Please, analyze the corporate governance report at this URL: {report_url}"
        )

        try:
            response: RunResponse = self.agent.run(prompt, stream=False)
        except Exception as e:
            logger.error(f"Error in {self.agent.name}.")
            raise e

        if response.content is None:
            raise ValueError(f"Missing response content.")

        if not isinstance(response.content, ReportResultsTemp):
            raise TypeError(f"Expected ReportResults, got {type(response.content)}.")

        return response.content

    def add_elements(self, elements) -> None:
        self.elements = elements
        self.agent.add_tool(PDFTools(elements))
