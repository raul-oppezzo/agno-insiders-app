import time
from typing import Iterator

from agno.agent import Agent
from agno.workflow import RunResponse, Workflow
from agno.utils.log import logger

from agents.report_search_agent import ReportSearchAgent
from agents.report_analyze_agent import ReportAnalyzeAgent

from models.report_url import ReportURL


class InsidersWorkflow(Workflow):
    """
    A workflow to search search for companies insiders on the web.
    """

    report_search_agent: Agent = ReportSearchAgent()
    report_analyze_agent: Agent = ReportAnalyzeAgent()

    def run(self, company_name: str) -> Iterator[RunResponse]:
        """
        Run the workflow to search for insiders of a company.

        Args:
            company_name (str): The name of the company to search for.
        """

        try:
            report_url: ReportURL = self.report_search_agent.search_report(company_name)

            if report_url.url is None or report_url.url == "":
                logger.warining(
                    f"Could not find the corporate governance report for '{company_name}'."
                )
                return RunResponse(
                    content=f"Sorry, could not find the corporate governance report for '{company_name}'.",
                )

            logger.info(f"Found report at {report_url.url}.")

            time.sleep(15)

            report_results = self.report_analyze_agent.analyze_report(
                # "https://www.leonardo.com/documents/15646808/16736911/RCG+2025_11+03+2025_ENG.pdf?t=1741706617319"
                report_url
            )

            return RunResponse(
                content=report_results,
            )
        except Exception as e:
            logger.error(f"An error occurred during the workflow: {str(e)}")
            raise RuntimeError(
                f"An error occurred during the workflow: {str(e)}"
            ) from e
