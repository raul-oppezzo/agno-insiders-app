from pydantic import BaseModel, Field


# This model will be used to structure the output of the search agent
class ReportURL(BaseModel):
    url: str = Field(
        default="", description="The URL of the corporate governance report."
    )
