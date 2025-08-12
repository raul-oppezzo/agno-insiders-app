from textwrap import dedent
from typing import Iterator, List, Optional
from pydantic import BaseModel, Field

from agno.agent import Agent, RunResponse
from agno.workflow import Workflow
from agno.models.google import Gemini
from agno.tools.googlesearch import GoogleSearchTools
from agno.tools.reasoning import ReasoningTools
from agno.utils.pprint import pprint_run_response
from agno.utils.log import log_debug, log_warning

from tools.crawl import CrawlTools
from tools.pdf import PDFTools


# This model will be used to structure the output of the search agent
class Report(BaseModel):
    url: Optional[str] = Field(
        default=None, description="The URL of the corporate governance report."
    )


# This model will be used to structure the output of the report agent
class Position(BaseModel):
    title: str = Field(description="The title of the position held by the insider.")
    entity: str = Field(
        description="The entity where the position is held (e.g., 'Board of Directors', 'Audit Committee')."
    )
    reports_to: str = Field(
        description="The entity to which the insider reports based on the position (e.g., 'Board of Directors', 'CEO')."
    )
    date_of_first_appointment: Optional[str] = Field(
        default=None, description="The date of first appointment to the position."
    )


# This model will be used to structure the output of the report agent for each insider
class Insider(BaseModel):
    name: str = Field(description="The name of the insider.")
    positions: List[Position] = Field(
        description="A list of positions held by the insider, including title, entity, reports to, and date of first appointment."
    )
    date_of_birth: Optional[str] = Field(
        default=None, description="The date of birth of the insider."
    )
    city_of_birth: Optional[str] = Field(
        default=None, description="The city of birth of the insider."
    )
    additional_info: Optional[str] = Field(
        default=None,
        description="Any additional relevant information about the insider.",
    )


class TempWorkflow(Workflow):
    """This workflow is designed to find the latest corporate governance report of a specified company. Analyze the report and extract relevant information about the governance of the company."""

    # An agent designed to search for corporate governance reports
    search_agent = Agent(
        model=Gemini(id="gemini-2.5-flash", temperature=0.1, top_p=0.95),
        tools=[
            GoogleSearchTools(fixed_max_results=5, cache_results=True),
            CrawlTools(max_length=25000, cache_results=True),
            ReasoningTools(add_instructions=True),
        ],
        description=dedent(
            """
            You are part of a workflow that is designed to analyze and extract information about the governance structure of companies and key personnel, and synthesize those informations into a knowledge graph.
            You are the first step of the workflow, and your task is to find the URL of the latest corporate governance report of the company specified by the user.
            """
        ),
        context=[
            "Corporate governance reports are typically found on the official website of the company, often under sections like 'Investor Relations' or 'Corporate Governance'.",
            "The report may be in PDF format or available as a webpage.",
            "Companies usually publish corporate governance reports annually on their websites and provide a list of past reports as well, you have to check the year of the reports available and return the latest one.",
            "The user is interested in italian companies reports, notice that the website may be in italian language, and the report name may be in italian as well",
        ],
        instructions=dedent(
            """
            Follow these instructions carefully:
            
            1. 🌐 Use 'google_search' tool to search for the corporate governance section of the company's website. Example query: "[company_name] governance".
            2. 🔍 Select the most relevant page and use the 'crawl' tool to extract the content of that page. Analyze the content and search for a reference to the latest corporate governance report within the crawled content.
            3. If the report is found, extract the URL and return it in the format: '{"url": "http://example.com/report.pdf"}'.
            4. If no report is found, analyze the crawled content to determine if there are any linked pages that might contain the report. Follow the links and crawl those pages as well to find the report.
            5. If no report can be found, return an empty URL: '{"url": null}'.

            ## Considerations:
            - Ensure the URL is complete and is the one of the latest corportate governance report (if available).
            - You should use few tool calls and avoid unnecessary ones, you have only to find the URL of the latest corporate governance report, do not try to extract the content of the report or analyze it, because it is done in the next step of the workflow.
            - If the governance report is not available, but the financial report is available, you can return the URL of the latest financial report available as well.
            - Skip any document that is has not a corporate governance report, or financial report, even if it is in governance section of the website.
            - Sometimes companies may not publish reports online, but they list the board members and other executives directicly on their website pages. I will crawl those pages in the next step of the workflow if no report is found.
            """
        ),
        show_tool_calls=True,
        tool_call_limit=15,
        use_json_mode=True,
        response_model=Report,
        debug_mode=True,
        exponential_backoff=True,
        retries=3,
        add_datetime_to_instructions=True,
    )

    report_agent = Agent(
        model=Gemini(id="gemini-2.5-flash", temperature=0.1, top_p=0.95),
        tools=[ReasoningTools(add_instructions=True), PDFTools()],
        description=dedent(
            """
            You are part of a workflow that is designed to analyze and extract information about the insiders of a company, and synthesize those informations into a knowledge graph.
            You are the second step of the workflow, and your task is to analyze the corporate governance report available at the URL provided by the search agent, and identify all the insiders of the company specified by the user. For each insider you have also to extract:
            - Name
            - Positions: 
                - title of the position (full title, e.g., "Executive Director", "Independent Director", "Chief Executive Officer", "Chief Financial Officer", etc.)
                - the entity the position is held in (e.g., "Board of Directors", "Audit Committee", etc.)
                - the entity to which the insider reports based on the position ("Board of Directors", "CEO", "Stakeholders", etc.)
                - Date of first appointment to the position
            - Date of birth
            - City of birth
            - Additional information (less than 10 lines): any other relevant information about the insider that can be found in the report, such as education, experience, or other roles held within other companies.
            """
        ),
        context=[
            dedent(
                """The reports you have to scan belongs to italian companies, usually their governance model is structured as follows:
                - board of directors (approves the financial statements, manages the company). Is composed by directors which can be executive or non-executive, independent or not. Usually there is a chairman, a lead independent director and a president of the board of directors.
                - board of statutory auditors (supervises the board of directors, ensures compliance with laws and regulations). Usually there is a president of the board of statutory auditors and other members. The board of statutory auditors is composed by independent members.
                - top managers (responsible for the day-to-day management of the company). Usually there is a Chief Executive Officer (CEO), other can be Chief Financial Officer (CFO), Chief Operating Officer (COO), etc.
                - committees (support the board of directors in specific areas, e.g. audit committee, compensation committee, etc.). Usually there is a chairman and other members.
                - auditors (legal advisors, external auditors)."""
            ),
            dedent(
                """Insiders are individuals who have access to non-public information about a company because of their position within the company. They can be:
                - directors: members of the board of directors. The board of directors is responsible for the overall management of the company. The members of the board of directors can be executive, non-executive, independen
                - auditors: members of the board of statutory auditors.
                - managers: senior management roles that oversee specific departments or functions. Can be part of the board of directors.
                - members of internal committees: usually are members of the board of directors."""
            ),
            dedent(
                """Usually:
                - president and chairman of the board of directors reports to the shareholders' meeting.
                - directors report to the board of directors.
                - chairman of the board of statutory auditors reports to the shareholders' meeting.
                - auditors report to the board of statutory auditors.
                - CEO reports to the board of directors.
                - other managers report to the CEO or the board of directors."""
            ),
        ],
        instructions=dedent(
            """
            Follow these instructions carefully:
            
            1. 📄 Use 'extraxt_text_from_url' tool to extract the content of the corporate governance report available at the URL provided by the search agent.
            2. 🕵️‍♂️ Analyze the content to identify all individuals listed in the report as part of the company's governance structure.
            3. 👥 Extract all the required informations about these individuals.
            4. Return a structured response containing all extracted insiders information.
            
            ## Considerations:
            - If you cannot find a specific information about an insider, you can skip that information, but try to extract as much information as possible.
            - If no insiders are found in the report, return an empty list: [].
            - If you cannot read the report return an empty list: [].
            """
        ),
        show_tool_calls=True,
        tool_call_limit=10,
        use_json_mode=True,
        response_model=List[Insider],
        # debug_mode=True,
        exponential_backoff=True,
        retries=3,
    )

    def run(self, company_name: str) -> Iterator[RunResponse]:
        report_url = None
        insiders_list = []

        try:
            search_agent_output = self.search_agent.run(
                f"Please provide the URL of the latest corporate governance report of the company {company_name}."
            )

            if not isinstance(search_agent_output.content, Report):
                log_warning("Unexpected output type from search agent.")
            else:
                report_url = search_agent_output.content.url
        except Exception as e:
            log_warning(f"Error running search agent: {e}")
            return

        try:
            report_agent_output = self.report_agent.run(
                f"Please analyze the corporate governance report available at {report_url} and extract all the insiders of the company {company_name}.",
            )

            if not isinstance(report_agent_output.content, List[Insider]):
                log_warning("Unexpected output type from report agent.")
            else:
                insiders_list = report_agent_output.content
        except Exception as e:
            log_warning(f"Error running report agent: {e}")
            return

        for insider in insiders_list:
            print(insider.model_dump(exclude_none=True, indent=2) + "\n")

        return RunResponse(
            content="completed",
        )
