"""HTTP request contracts; domain policy contracts live with their features."""

from pydantic import BaseModel, Field


class LoginInput(BaseModel):
    organization: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class BranchInput(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    tier: str | None = Field(default="KCU", max_length=40)
    menus: list[str] | None = None


class BranchUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    tier: str | None = Field(default=None, max_length=40)
    menus: list[str] | None = None


class UserInput(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=200)
    role: str
    branches: list[str] = Field(min_length=1, max_length=100)


class PreviewInput(BaseModel):
    filenames: list[str] = Field(max_length=100)


class SpiderResubmit(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    accept_possible_duplicate_charge: bool


class RegroupInput(BaseModel):
    labels: dict[str, str]
    revision: str
    reason: str = Field(min_length=5, max_length=1000)


class ComparisonInput(BaseModel):
    expected_revision: int = Field(ge=0)
    sample_id: str
    documents: dict[str, str] = Field(default_factory=dict)
    edits: dict[str, object] = Field(default_factory=dict)
    reason: str = Field(min_length=5, max_length=1000)


class ContextInput(BaseModel):
    values: dict
    reason: str = Field(min_length=5, max_length=1000)
    evidence: str = Field(min_length=5, max_length=1000)


class CaseConfigurationInput(BaseModel):
    expected_version: int = Field(ge=1)
    target_version: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=1000)


class FindingReview(BaseModel):
    report_id: str | None = None
    rule_id: str
    result: str
    reason: str = Field(min_length=10, max_length=1000)
    observations: list[dict] = Field(min_length=1, max_length=20)


class VisualBoxReview(BaseModel):
    field: str = Field(min_length=1, max_length=200)
    page_number: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    learn_for_future: bool = True
    reason: str = Field(min_length=5, max_length=1000)


class ReprocessFieldsInput(BaseModel):
    fields: list[str] = Field(min_length=1, max_length=100)
    instruction: str = Field(default="", max_length=10000)
    reason: str = Field(min_length=3, max_length=2000)
    use_latest_config: bool = True
    replace_overrides: bool = False
    save_to_profile: bool = True


class RetryFieldsInput(BaseModel):
    accept_possible_duplicate_charge: bool = False


class ClassificationInput(BaseModel):
    doc_type: str
    reason: str = Field(min_length=5, max_length=1000)


class CorrectionInput(BaseModel):
    field: str
    value: object
    reason: str = Field(min_length=5, max_length=1000)


class EffectiveCorrectionInput(CorrectionInput):
    expected_value: object


class MoveInput(BaseModel):
    case_id: str
    reason: str = Field(min_length=5, max_length=1000)


class ReconcileInput(BaseModel):
    stage: str
    provider_id: str = Field(min_length=5, max_length=100)
    reason: str = Field(min_length=5, max_length=1000)


class TaskAssignment(BaseModel):
    assigned_to: str | None = None
    due_at: float | None = Field(default=None, ge=0)


class EnumRevalidationInput(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
