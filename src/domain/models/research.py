"""Domain models for Research Agent feature"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl


ResearchMode = Literal["speed", "balanced", "quality"]


class Citation(BaseModel):
    """A cited source in the research report"""

    url: HttpUrl
    title: str
    snippet: str


class Fact(BaseModel):
    """An extracted factual claim from a source"""

    claim: str
    source_url: HttpUrl
    confidence: float = Field(ge=0.0, le=1.0)


class ResearchStats(BaseModel):
    """Execution statistics for a research task"""

    iterations: int
    urls_visited: int
    elapsed_seconds: float
    mode_used: str
    beast_mode_triggered: bool = False


class ResearchReport(BaseModel):
    """The final research report output"""

    query: str
    mode: str
    answer_markdown: str
    citations: list[Citation] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    stats: ResearchStats


class ResearchRequest(BaseModel):
    """User request to start a research task"""

    query: str = Field(..., min_length=3, max_length=2000)
    mode: ResearchMode = "balanced"
    max_iters: Optional[int] = Field(default=None, ge=1, le=20)
    max_tokens: Optional[int] = Field(default=None, ge=1000, le=32000)


class ResearchTaskStatus(BaseModel):
    """Status response for a research task"""

    task_id: str
    status: Literal["pending", "running", "completed", "failed"]
    progress: Optional[dict] = None
    result: Optional[ResearchReport] = None
    created_at: str
    updated_at: Optional[str] = None


class ResearchTaskCreateResponse(BaseModel):
    """Response when creating a new research task"""

    task_id: str
    status: str = "pending"
    message: str = "Research task queued"
