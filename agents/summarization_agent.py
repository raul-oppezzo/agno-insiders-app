from agno.agent import Agent, RunResponse
from agno.models.google import Gemini
from agno.utils.log import logger

from exceptions.exceptions import AgentException
from models.report_results import ReportResultsTemp

from prompts.summarization_agent_prompt import (
    DESCRIPTION,
    INSTRUCTIONS,
    ADDITIONAL_CONTEXT,
)


class SummarizationAgent:
    """An agent to validate the report results."""

    def __init__(self):
        self.agent = Agent(
            name="SummarizationAgent",
            model=Gemini(
                id="gemini-2.5-flash",
                temperature=0.1,
                top_p=0.95,
            ),
            description=DESCRIPTION,
            instructions=INSTRUCTIONS,
            additional_context=ADDITIONAL_CONTEXT,
            use_json_mode=True,
            response_model=ReportResultsTemp,
            debug_mode=False,
            exponential_backoff=True,
            retries=2,
            delay_between_retries=30,  # Timeout of 30 seconds
        )

    def summarize_results(self, results: list[dict]) -> ReportResultsTemp:
        """
        Runs the agent to summarize the results extracted from the report chunks.

        Args:
            results (list[dict]): The results to be summarized.

        Returns:
            ReportResultsTemp: The summarized results.
        """

        prompt = f"""Please summarized and merge the following chunk results.
        
        **RESULTS**:
        \"\"\"
        {results}
        \"\"\"

        **OUTPUT**: 
        """

        try:
            response: RunResponse = self.agent.run(prompt, stream=False)
        except Exception as e:
            message = f"Error in {self.agent.name}."
            raise AgentException(message) from e

        if response.content is None:
            raise AgentException(f"Missing response content.")

        if not isinstance(response.content, ReportResultsTemp):
            raise AgentException(f"Expected ReportResults, got {type(response.content)}.")

        return response.content
