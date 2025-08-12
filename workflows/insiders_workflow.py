from datetime import datetime
import os
from textwrap import dedent
import time
from typing import Iterator, List, Optional
from pydantic import BaseModel, Field
import json

from agno.agent import Agent, RunResponse
from agno.workflow import Workflow
from agno.run.response import RunEvent
from agno.models.google import Gemini
from agno.tools.googlesearch import GoogleSearchTools
from agno.tools.reasoning import ReasoningTools
from agno.tools.sleep import SleepTools
from agno.utils.pprint import pprint_run_response
from agno.utils.log import log_debug, log_warning

from tools.crawl import CrawlTools
from tools.pdf import PDFTools


class Role(BaseModel):
    role_name: Optional[str] = Field(None, description="name of the role")
    reports_to: Optional[str] = Field(
        None,
        description="who the role reports to based on the corporate governance model",
    )
    member_of: Optional[str] = Field(
        None, description="the board or committee the role belongs to (if any)"
    )
    date_of_first_appointment: Optional[str] = Field(
        None, description="date of first appointment (if available). Format: dd-MM-YYYY"
    )


class Insider(BaseModel):
    name: Optional[str] = Field(..., description="name of the insider")
    roles: Optional[List[Role]] = Field(
        None, description="list of specific roles held by the insider"
    )
    date_of_birth: Optional[str] = Field(
        None,
        description="date of birth of the insider (if available). Format: dd-MM-YYYY",
    )
    city_of_birth: Optional[str] = Field(
        None, description="city of birth of the insider (if available)"
    )
    other_info: Optional[str] = Field(
        None, description="any other information about the insider (few lines summary)"
    )


class GovernanceReportResults(BaseModel):
    url: str = Field(None, description="URL of the governance report")
    insiders: List[Insider] = Field(
        None, description="list of insiders found in the report"
    )


class SearchResult(BaseModel):
    insider: Insider
    source: str = Field(None, description="source used for this result")


class SearchResults(BaseModel):
    results: List[SearchResult] = Field(None, description="list of search results")


class InsidersWorkflow(Workflow):
    """Workflow to search for insiders of a company"""

    # An agent to scan corporate governance reports
    governance_report_agent = Agent(
        name="Governance Report Agent",
        model=Gemini(id="gemini-2.5-flash", temperature=0.1, top_p=0.95),
        tools=[
            GoogleSearchTools(fixed_max_results=3, cache_results=True),
            PDFTools(cache_results=True),
            CrawlTools(max_length=50000, cache_results=True),
            ReasoningTools(add_instructions=True),
        ],
        system_message=dedent(
            """
            You are an agent specialized in corporate governance.

            <task>
            Your specific task is to search the web, find the latest annual governance report of a company specified by the user and extract all the insiders (see **context** section below).
            For each insider you have also to extract the following information:
            - name
            - role (be specific, see **context** section below)
            - who the insider reports to based on his role (see **context** section below)
            - date of birth (if available, in the format dd-MM-YYYY)
            - country of birdth (if available)
            - date of first appointment (if available, in the format dd-MM-YYYY)
            - any other information you can find about the insider (few lines summary)
            </task>

            <context>
                <corporate_governance_model>
                We are interested in italian companies, usually these companies corporate governance model is structured as follows:
                - board of directors (approves the financial statements, manages the company). Is composed by directors which can be executive or non-executive, independent or not. Usually there is a chairman, a lead independent director and a president of the board of directors.
                - board of statutory auditors (supervises the board of directors, ensures compliance with laws and regulations). Usually there is a president of the board of statutory auditors and other members. The board of statutory auditors is composed by independent members.
                - top managers (responsible for the day-to-day management of the company). Usually there is a Chief Executive Officer (CEO), other can be Chief Financial Officer (CFO), Chief Operating Officer (COO), etc.
                - committees (support the board of directors in specific areas, e.g. audit committee, compensation committee, etc.). Usually there is a chairman and other members.
                - auditors (legal advisors, external auditors).
                </corporate_governance_model>

                <insiders>
                Insiders are individuals who have access to non-public information about a company because of their position within the company. They can be:
                - directors: members of the board of directors.
                - auditors: members of the board of statutory auditors.
                - managers: senior management roles that oversee specific departments or functions. Can be part of the board of directors.
                - members of internal committees: usually are members of the board of directors.
                </insiders>

                <reports_to_chain>
                Usually:
                - president and chairman of the board of directors reports to the shareholders' meeting.
                - directors report to the board of directors.
                - chairman of the board of statutory auditors reports to the shareholders' meeting.
                - auditors report to the board of statutory auditors.
                - CEO reports to the board of directors.
                - other managers report to the CEO or the board of directors.
                </reports_to_chain>
            </context>

            <instructions>
            Follow these instructions carefully:
            1. Search for the latest annual governance report of the company using **google_search_tools**. Start with a general query like "company_name corporate governance".
            2. Scan the search results for the URL of the governance report in PDF format:
               - If the report URL is in search results: use the **pdf_tools** to extract the content of the report.
               - If the report URL is NOT in search results: use the **crawl_tools** to crawl the pages returned by the search query and search a reference to the report.
            3. When you have the report content, extract all the insiders and their information.
            </instructions>

            <considerations>
            - If the PDF is not in the search results, you have to crawl the web pages returned in the search results to find a reference to the report. These pages can be trickier to parse, and may contain references to all the annual reports of the company, so you have to be careful to extract the correct one (the latest).
            - Avoid scanning PDFs from unofficial sources, or that are NOT linked from the official company website.
            - If some information is not available in the report, just leave it empty. Be sure to search the information before leaving it empty.
            - Use the **reasoning_tools** to plan your actions.
            - Be sure to exctract the governance report, not the financial report or other types of reports.
            - Be sure to extract the report of the company specified by the user.
            - Do NOT compose search queries that are too long or complex, keep them simple and with few keywords. Example: "company_name documenti governance", "company_name governance", "company_name investors", etc.
            - Refine your queries based on the results you get, if you don't find the report in the first attempt.
            </considerations>
            """
        ),
        debug_mode=True,
        show_tool_calls=True,
        tool_call_limit=10,
        add_datetime_to_instructions=True,
        exponential_backoff=True,
        retries=3,
        use_json_mode=True,
        response_model=SearchResults,
    )

    # An agent to search the insiders on the web
    insiders_web_agent = Agent(
        name="Insiders Crawl Agent",
        model=Gemini(id="gemini-2.5-flash", temperature=0.1, top_p=0.95),
        tools=[
            GoogleSearchTools(
                fixed_max_results=5, cache_results=True
            ),  # Cache results during testing
            CrawlTools(max_length=25000, cache_results=True, governance_mode=False),
            ReasoningTools(add_instructions=True),
        ],
        system_message=dedent(
            """
            You are an advanced web search agent specialized in corporate governance.
            
            <task>
            Your specific task is to search the web, find and extract all the insiders (see **context section beloe).
            For each insider you have also to extract the following information:
            - name
            - role (be specific, see **context section below**)
            - who the insider reports to based on his role (see **context section below**)
            - date of birth (if available, in the format dd-MM-YYYY)
            - city of birth (if available)
            - date of first appointment (if available, in the format dd-MM-YYYY)
            - any other information you can find about the insider (few lines summary)
            </task>

            <context>
                <corporate_governance_model>
                We are interested in italian companies, usually these companies corporate governance model is structured as follows:
                - board of directors (approves the financial statements, manages the company). Is composed by directors which can be executive or non-executive, independent or not. Usually there is a chairman, a lead independent director and a president of the board of directors.
                - board of statutory auditors (supervises the board of directors, ensures compliance with laws and regulations). Usually there is a president of the board of statutory auditors and other members. The board of statutory auditors is composed by independent members.
                - top managers (responsible for the day-to-day management of the company). Usually there is a Chief Executive Officer (CEO), other can be Chief Financial Officer (CFO), Chief Operating Officer (COO), etc.
                - committees (support the board of directors in specific areas, e.g. audit committee, compensation committee, etc.). Usually there is a chairman and other members.
                - auditors (legal advisors, external auditors).
                </corporate_governance_model>

                <insiders>
                Insiders are individuals who have access to non-public information about a company because of their position within the company. They can be:
                - directors: members of the board of directors.
                - auditors: members of the board of statutory auditors.
                - managers: senior management roles that oversee specific departments or functions. Can be part of the board of directors.
                - members of internal committees: usually are members of the board of directors.
                </insiders>

                <reports_to_chain>
                Usually:
                - president and chairman of the board of directors reports to the shareholders' meeting.
                - directors report to the board of directors.
                - chairman of the board of statutory auditors reports to the shareholders' meeting.
                - auditors report to the board of statutory auditors.
                - CEO reports to the board of directors.
                - other managers report to the CEO or the board of directors.
                </reports_to_chain>
            </context>

            <instructions>
            Follow these instructions carefully:
            1. Search: create a search query and pass it to **google_search** tool.
            2. Crawl: for each result pass the page URL to the **crawl_tools** tool to get the page content (DO NOT crawl URLs that you have already crawled).
            3. Extract: read the page content and extract ALL the information about the insiders (Note: the page content is unstructured). DO NOT follow any link on the page, just read the content and extract the information you need.
            4. Loop: if you have not found enough information or you think you counld potentially find more information repeat from step 1
            </instructions>

            <considerations>
            - Always crawl the official company website. It usually has the most complete and updated information about the insiders. It usually has sections like "governance", "management", etc.
            - Be sure to search for all the categories of insiders (see **context** section).
            - For each result output the exact source were you found the information
            - Avoid duplicated results, add multiple sources instead.
            - DO NOT crawl PDF files or corporate governance reports.
            - When you have crawled 20 URLs you have to stop and return the results. Use the **reasoning_tools** to decide if you have to stop or not.
            - If you DO NOT find any insider return an empty string.
            </considerations>
        """
        ),
        debug_mode=True,
        show_tool_calls=True,
        tool_call_limit=50,
        exponential_backoff=True,
        retries=3,
        use_json_mode=True,
        response_model=SearchResults,
    )

    def run(self, company_name: str) -> Iterator[RunResponse]:
        """
        Run the insiders search workflow.
        """

        governance_report_agent_response = self.governance_report_agent.run(
            f"Please search the web to find the latest governance report of the company {company_name} and extract all the insiders and informations related.",
        )

        if not isinstance(
            governance_report_agent_response.content, GovernanceReportResults
        ):
            log_warning(
                f"Governance report agent failed to find governance report for {company_name}."
            )
            return RunResponse(
                content="Failed to crawl governance report.",
            )

        # Sleep for 15 seconds to avoid rate limiting issues
        time.sleep(15)

        insiders_web_agent_response = self.insiders_web_agent.run(
            f"Please search the web to find all the insiders of the company {company_name} and extract all the insiders and informations related.",
        )

        if not isinstance(insiders_web_agent_response.content, SearchResults):
            log_warning(
                f"Insiders web agent failed to find insiders for {company_name}."
            )
            return RunResponse(
                content="Failed to crawl insiders.",
            )

        os.makedirs("../results", exist_ok=True)

        # Prepare results data
        results_data = {
            "company_name": company_name,
            "timestamp": datetime.now().isoformat(),
            "governance_report": governance_report_agent_response.content.model_dump(),
            "web_search": insiders_web_agent_response.content.model_dump(),
            "status": "success",
        }

        filename = f"{company_name.replace(' ', '_').lower()}_insiders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join("../results", filename)

        with open(filepath, "w") as f:
            json.dump(results_data, f, indent=2, ensure_ascii=False)

        print(f"\nResults saved to: {filepath}")

        return RunResponse(
            content="Workflow completed successfully.",
        )