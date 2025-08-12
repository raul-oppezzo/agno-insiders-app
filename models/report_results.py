from typing import Optional, List
from pydantic import BaseModel, Field


class Role(BaseModel):
    insider_name: str = Field(
        ..., description="The name of the insider holding the role."
    )
    governing_body: Optional[str] = Field(
        default=None,
        description="The governing body to which the role belongs (e.g., 'board of directors') if any.",
    )
    title: str = Field(
        ...,
        description='The title of the role held by the insider (e.g. "executive director", "lead independent director").',
    )
    date_of_first_appointment: Optional[str] = Field(
        default=None,
        description="The date of first appointment to the position.",
    )


class Company(BaseModel):
    name: str = Field(
        ..., description="The name of the company to which the report belongs."
    )
    address: Optional[str] = Field(
        default=None, description="The legal address of the company."
    )
    isin: Optional[str] = Field(
        default=None, description="The ISIN code of the company."
    )
    vat_number: Optional[str] = Field(
        default=None, description="The VAT number of the company."
    )
    ticker: Optional[str] = Field(
        default=None, description="The ticker symbol of the company."
    )


class GoverningBody(BaseModel):
    name: str = Field(
        ..., description="The name of the governing body (e.g., 'board of directors')."
    )


class Insider(BaseModel):
    name: str = Field(..., description="The name of the insider.")
    date_of_birth: Optional[str] = Field(
        default=None, description="The date of birth of the insider."
    )
    city_of_birth: Optional[str] = Field(
        default=None, description="The city of birth of the insider."
    )


class ReportResults(BaseModel):
    report_url: str = Field(..., description="The URL of the analyzed report.")
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
