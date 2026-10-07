"""Error response schemas."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standardized API error response."""

    detail: str = Field(..., description="Description of the error that occurred.")
