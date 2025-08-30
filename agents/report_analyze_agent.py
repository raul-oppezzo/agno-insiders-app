from agno.agent import Agent, RunResponse
from agno.models.google import Gemini
from agno.utils.log import logger

from exceptions.exceptions import AgentException
from models.report_results import ReportResultsTemp
from prompts.report_analyze_agent_prompt import (
    DESCRIPTION_TEMP,
    ADDITIONAL_CONTEXT_TEMP,
    INSTRUCTIONS_TEMP,
)
from tools.pdf import PDFTools


class ReportAnalyzeAgent:

    def __init__(self):
        self.agent = Agent(
            name="ReportAnalyzeAgent",
            model=Gemini(
                id="gemini-2.5-flash",
                temperature=0.1,
                top_p=0.95,
            ),
            description=DESCRIPTION_TEMP,
            instructions=INSTRUCTIONS_TEMP,
            additional_context=ADDITIONAL_CONTEXT_TEMP,
            use_json_mode=True,
            response_model=ReportResultsTemp,
            debug_mode=True,
            exponential_backoff=True,
            retries=2,
            delay_between_retries=30,  # Timeout of 30 seconds
        )

    async def analyze_chunk_async(
        self, chunk_index: int, chunk_text: str
    ) -> ReportResultsTemp:
        """
        Search for the insiders and governance data in the given chunk.

        Args:
            chunk_index (int): The index of the chunk.
            chunk_text (str): The text of the chunk.

        Returns:
            ReportResults: The results of the analysis.
        """

        chunk_prompt = f""" 
            Please analyze this chunk of the corporate governance report:
            
            **CHUNK {chunk_index}**:
            \"\"\"
            {chunk_text}
            \"\"\"
            
            **OUTPUT**:
            """

        try:
            response: RunResponse = await self.agent.arun(chunk_prompt, stream=False)
        except Exception as e:
            message = f"Error in {self.agent.name}."
            raise AgentException(message) from e

        if response is None or response.content is None:
            message = f"Missing response content."
            raise AgentException(message)

        if not isinstance(response.content, ReportResultsTemp):
            message = f"Expected ReportResults, got {type(response.content)}."
            raise AgentException(message)

        return response.content

    ###################### Unused ###########################

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
