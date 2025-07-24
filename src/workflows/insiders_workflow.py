from textwrap import dedent
from typing import Iterator, List

from agno.agent import Agent, RunResponse
from agno.workflow import Workflow
from agno.run.response import RunEvent
from agno.utils.log import logger
from agno.models.google import Gemini
from agno.tools.googlesearch import GoogleSearchTools
from agno.tools.reasoning import ReasoningTools
from pydantic import BaseModel, Field

from tools.crawl import CrawlTools


class Result(BaseModel):
    url: str = Field(..., description="URL of the page")
    content: str = Field(..., description="Content of the page that contains information about insiders")
    
class SearchResults(BaseModel):
    results: List[Result] = Field(..., description="list of search results")

class InsidersWorkflow(Workflow):
    """Workflow to search for insiders of a company using web crawling."""

    # An agent to search the insiders on the web
    insiders_crawl_agent = Agent(
        name="Insiders Crawl Agent",
        model=Gemini(id="gemini-2.5-pro", temperature=0.1, top_p=0.95),
        tools=[
            GoogleSearchTools(cache_results=True, fixed_max_results=5), 
            CrawlTools(max_length=None, cache_results=True), 
            ReasoningTools(add_instructions=True)],
        description=dedent("""
            You are a web search agent specialized in finding the isiders of a given company and their roles (see context for definition of insiders). 
            Your task is to search the web to find ALL the insiders of the given company and for each insider the specific roles and responsibilities.
            You can search the web using **google_search_tools** and get pages content as markdown using **crawl_tools**.
        """),
        context=dedent("""
            ## INSIDERS DEFINITION:
                - Insiders are individuals who have access to non-public information about a company that could influence its stock price.
                - Insiders can be employees, directors, executives, managers, statutory auditors, legal advisors.
                - Companies do not disclose the names of insiders to the public, but only to regulatory authorities.
                - We can only know of **potential** insiders based on their roles, responsibilities, and relationships with the company. In the following will use the term "insiders" to refer to this category of individuals.
                - Insiders can be found in various sources such as company websites, press releases, financial reports, and news articles.
                - The roles and responsibilities of insiders can vary depending on the company and its structure. Generally, insiders can be categorized as follows:
                    - **board members**: Individuals who are part of the company's board of directors and are responsible for overseeing the company's management and making strategic decisions. Board members can be independent or not and could be part of internal committees such as audit, compensation, or governance committees.
                    - **top managers**: Senior executives who are responsible for the overall management and direction of the company or specific departments. CEOs, CFOs, and COOs are examples of top managers.
                    - **statutory auditors**: Individuals who are responsible for auditing the company's financial statements and ensuring compliance with legal and regulatory requirements.
                    - **legal advisors**: Professionals who provide legal advice and support to the company, including contract negotiations, compliance issues, and litigation matters.
        """),
        instructions=dedent("""
            You have to implement a search loop following these steps:
                1. Search the web using **google_search_tools** to find pages that mention the insiders of the company. Pass the tool a **search query**, the tool will return a list of page urls that potentially contain the informations you need.
                2. For each returned page url get the content using **crawl_tools**. Pass the tool a **page_url** and it will return the page content as markdown. Read ALL the page content and extract ALL the informations about the insiders. You donn't have to follow any link, just read the page content.
                3. Final loop step (conditional step): if you have found enough information about the insiders, you can stop the search and return the results. Otherwise, you can continue searching for more pages.

            ## IMPORTANT CONSTRAINTS:
            - Be thorough and exhaustive in your search, do not skip any page that might contain useful information.
            - DO NOT repeat the search loop for more than 10 times (It's a MUST). BUT DO at least 3 iterations.
            - Multiple pages may contain the same information, don't worry about duplicates, just extract all the information you can find.
            - Start by general searches and then narrow down the search to specific pages that might contain informations you don't have found in the previos loop cycles.
            - The final OUTPUT must be a list of sources (page urls) and the extracted information about the insiders. The information must be complete and detailed, but in a concise format.
        """),
        debug_mode=True,
        show_tool_calls=True,
        exponential_backoff=True,
        tool_call_limit=50,
        add_datetime_to_instructions=True,
        markdown=True,
        retries=5,
        use_json_mode=True,
        response_model=SearchResults,
    )

    def run(self, company_name: str) -> Iterator[RunResponse]:
        yield from self.insiders_crawl_agent.run(f"Please search the web to find information about the insiders of the company {company_name}.", stream=True)
