from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field





class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    severity: Severity
    service: str = Field(..., min_length=1)
    environment: str = Field(..., min_length=1)
    symptoms: str | None = Field(None, max_length=2000)


class IncidentResponse(IncidentCreate):
    id: int
    status: str = "open"
    created_at: datetime
    updated_at: datetime


class RecalledFromItem(BaseModel):
    incident_title: str = ""
    symptom: str = ""
    service: str = ""
    fix: str = ""


class RCAResponse(BaseModel):

    root_cause: str

    confidence: int

    recommended_fix: str

    first_action: str

    # The LLM is asked to echo which historical incidents it used, but this
    # field is DISCARDED by the service (recalled_from is rebuilt from the
    # recall chunks via _parse_recalled). Models return it as strings OR as
    # objects, so accept any list shape to avoid validation failures.
    recalled_from: list = Field(default_factory=list)


class IncidentResolveRequest(BaseModel):
    confirmed_root_cause: str = Field(..., min_length=1, max_length=2000)
    fix_applied: str = Field(..., min_length=1, max_length=2000)


class IncidentDetailResponse(IncidentResponse):
    root_cause: str | None = None
    confidence: int | None = None
    recommended_fix: str | None = None
    first_action: str | None = None
    recalled_from: list[RecalledFromItem] | None = None
    fix_applied: str | None = None


class Incident(BaseModel):
    id: int

    title: str

    severity: Severity

    service: str

    environment: str

    symptoms: str | None = None

    status: str

    created_at: datetime

    updated_at: datetime

    root_cause: str | None = None

    fix_applied: str | None = None