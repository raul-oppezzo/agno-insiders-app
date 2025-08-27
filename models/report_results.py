from typing import Optional, List
from pydantic import BaseModel, Field


class Role(BaseModel):
    insider_name: str = Field(
        ..., description="The full name of the insider holding the role."
    )
    governing_body: Optional[str] = Field(
        default=None,
        description="The governing body to which the role belongs (e.g., 'board of directors') if the role belongs to a governing body.",
    )
    title: str = Field(
        ...,
        description='The exact title of the role held by the insider (e.g. "executive director", "lead independent director").',
    )
    date_of_first_appointment: Optional[str] = Field(
        default=None,
        description="The date of first appointment to the position.",
    )
    description: str = Field(
        ..., description="A brief decription (max 50 characters) of the role."
    )


class Company(BaseModel):
    name: str = Field(
        ..., description="The name of the company to which the report belongs."
    )
    address: Optional[str] = Field(
        default=None, description="The legal address of the company."
    )
    tax_number: Optional[str] = Field(
        default=None, description="The tax number of the company."
    )
    isin: Optional[str] = Field(
        default=None, description="The ISIN code of the company."
    )
    ticker: Optional[str] = Field(
        default=None, description="The ticker symbol of the company."
    )


class GoverningBody(BaseModel):
    name: str = Field(
        ..., description="The name of the governing body (e.g., 'board of directors')."
    )
    description: str = Field(
        ...,
        description="A brief description of the governing body (like purpose and function).",
    )


class Insider(BaseModel):
    name: str = Field(..., description="The name of the insider.")
    date_of_birth: Optional[str] = Field(
        default=None,
        description="The date of birth of the insider (YYYY-MM-dd format).",
    )
    city_of_birth: Optional[str] = Field(
        default=None, description="The city of birth of the insider."
    )


class ReportResults(BaseModel):
    # report_url: str = Field(..., description="The URL of the analyzed report.")
    company: Company = Field(
        ..., description="The company to which the report belongs."
    )
    governing_bodies: List[GoverningBody] = Field(
        ..., description="A list of the governing bodies identified in the report."
    )
    insiders: List[Insider] = Field(
        ..., description="A list of insiders identified in the report."
    )
    roles: List[Role] = Field(..., description="A list of roles.")


class Node(BaseModel):
    id: str = Field(default="")
    label: str = Field(default="")
    properties: dict = Field(default={})


class Edge(BaseModel):
    source: str = Field(
        default="",
    )  # id of the source node
    type: str = Field(
        default="",
    )  # type of the relationship
    dest: str = Field(
        default="",
    )  # id of the target node
    properties: dict = Field(default={}) # additional properties of the edge


class ReportResultsTemp(BaseModel):
    nodes: List[Node] = Field(default=[])
    edges: List[Edge] = Field(default=[])
