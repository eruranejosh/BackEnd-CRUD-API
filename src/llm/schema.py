from pydantic import BaseModel, Field
from typing import Literal


class PropertyEnrichment(BaseModel):
    property_type: Literal[
        "apartment",
        "house",
        "duplex",
        "land",
        "office",
        "shop",
        "other",
    ]

    bedrooms: int | None = None

    location: str | None = None

    condition: Literal[
        "new",
        "renovated",
        "fair",
        "needs_renovation",
        "unknown",
    ]

    servicing: Literal[
        "serviced",
        "unserviced",
        "unknown",
    ]

    summary: str

    confidence: float = Field(ge=0.0, le=1.0)

    needs_review: bool

class PropertyInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
