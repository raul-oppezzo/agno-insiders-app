from agno.agent import Agent, RunResponse
from agno.models.google import Gemini

from exceptions.exceptions import AgentException
from models.report_results import ReportResults

from prompts.validation_agent_prompt import (
    DESCRIPTION,
    INSTRUCTIONS,
    # ADDITIONAL_CONTEXT,
)


class ValidationAgent:
    """An agent to validate the report results."""

    def __init__(self):
        self.agent = Agent(
            name="ValidationAgent",
            model=Gemini(
                id="gemini-2.5-flash",
                temperature=0.0,
            ),
            description=DESCRIPTION,
            instructions=INSTRUCTIONS,
            # additional_context=ADDITIONAL_CONTEXT,
            use_json_mode=True,
            response_model=ReportResults,
            debug_mode=False,
            exponential_backoff=True,
            retries=2,
            delay_between_retries=30,  # Timeout of 30 seconds
        )

    def validate_results(self, results: dict) -> ReportResults:
        """
        Runs the agent to validate the resutlts extracted from the report.

        Args:
            data (list[dict]): The data to be verified.

        Returns:
            ReportResults: The verified data.
        """

        prompt = f"""Please validate the following data:
        
        \"\"\"
        {results}.
        \"\"\"

        Validated Output: 
        """

        try:
            response: RunResponse = self.agent.run(prompt, stream=False)
        except Exception as e:
            message = f"Error in {self.agent.name}."
            raise AgentException(message) from e

        if response.content is None:
            raise AgentException(f"Missing response content.")

        if not isinstance(response.content, ReportResults):
            raise AgentException(f"Expected ReportURL, got {type(response.content)}.")

        return response.content
