from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500, description="研究主题")
    max_iterations: int = Field(default=3, ge=1, le=10, description="最大迭代次数")


class ResearchStatusResponse(BaseModel):
    task_id: str
    topic: str
    status: str
    progress: str
    report_path: str | None = None


class ReportListItem(BaseModel):
    filename: str
    created_at: str
    size: int
