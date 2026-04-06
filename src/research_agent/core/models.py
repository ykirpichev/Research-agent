"""Core data models for Research Agent."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class IdeaStatus(str, Enum):
    """Status of an exploratory idea."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    EXPLORED = "explored"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    DEFERRED = "deferred"


class ToolName(str, Enum):
    """Available sandbox tools."""

    SEARCH = "search"
    READ = "read"
    LIST = "list"
    RESOLVE = "resolve"
    RUN = "run"


class MemoryType(str, Enum):
    """Types of memories learned by the agent."""

    PATTERN = "pattern"
    DOMAIN = "domain"
    CONNECTION = "connection"
    TOOL_SIGNAL = "tool_signal"


class RunStatus(str, Enum):
    """Status of a research run."""

    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"
    ABORTED = "aborted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ERROR = "error"


class ExplorationArea(BaseModel):
    """Defines the scope for code exploration."""

    roots: list[str] = Field(
        ..., description="Root paths to explore (e.g., ['src/', 'lib/'])"
    )
    include_patterns: Optional[list[str]] = Field(
        default=None, description="Glob patterns to include (e.g., ['*.py', '*.go'])"
    )
    exclude_patterns: Optional[list[str]] = Field(
        default=None,
        description="Glob patterns to exclude (e.g., ['*_test.py', '**/__pycache__'])",
    )
    natural_language_hint: Optional[str] = Field(
        default=None,
        description="Natural language description of the area (e.g., 'authentication and session management')",
    )


class ExploratoryIdea(BaseModel):
    """One exploratory hypothesis or thread to investigate."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique idea ID")
    title: str = Field(..., description="Short, actionable title (3-10 words)")
    hypothesis: str = Field(..., description="What we want to understand or learn")
    priority: int = Field(
        default=3, ge=1, le=5, description="Priority score (1=low, 5=high)"
    )
    status: IdeaStatus = Field(default=IdeaStatus.QUEUED, description="Current status")
    parent_id: Optional[str] = Field(
        default=None, description="ID of parent idea if this is a follow-up"
    )
    effort_estimate: int = Field(
        default=2, ge=1, le=5, description="Estimated effort (1=simple, 5=complex)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    findings: list[str] = Field(
        default_factory=list, description="Accumulated findings for this idea"
    )
    block_reason: Optional[str] = Field(
        default=None, description="Why idea is blocked, if applicable"
    )
    tool_call_count: int = Field(
        default=0, description="Number of tool calls used for this idea"
    )


class ToolTrace(BaseModel):
    """Record of a tool execution."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique trace ID")
    tool_name: ToolName = Field(..., description="Which tool was executed")
    args_summary: str = Field(
        ..., description="Summary of tool arguments (not full args)"
    )
    idea_ids: list[str] = Field(
        default_factory=list, description="IDs of ideas this trace is linked to"
    )
    duration_seconds: float = Field(..., description="Execution time in seconds")
    stdout_excerpt: Optional[str] = Field(
        default=None, description="First 500 chars of stdout"
    )
    stderr_excerpt: Optional[str] = Field(
        default=None, description="First 500 chars of stderr"
    )
    success: bool = Field(..., description="Whether tool executed successfully")
    error_message: Optional[str] = Field(
        default=None, description="Error message if failed"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Finding(BaseModel):
    """A discovery from code exploration."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique finding ID")
    summary: str = Field(..., description="Human-readable finding summary (1-3 sentences)")
    idea_id: str = Field(..., description="ID of the idea this finding relates to")
    tool_trace_ids: list[str] = Field(
        default_factory=list,
        description="Tool traces that led to this finding",
    )
    code_locations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="File/line references (e.g., [{'file': 'auth.py', 'line': 42, 'symbol': 'authenticate'}])",
    )
    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Confidence in this finding (0-1)"
    )
    is_speculative: bool = Field(
        default=False, description="Whether this is inference vs direct observation"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Memory(BaseModel):
    """Learned artifact from exploration."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique memory ID")
    memory_type: MemoryType = Field(..., description="Type of memory")
    summary: str = Field(..., description="Concise summary of what was learned")
    description: Optional[str] = Field(
        default=None, description="Extended description if needed"
    )
    code_references: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Code locations referenced in this memory",
    )
    related_ideas: list[str] = Field(
        default_factory=list, description="IDs of ideas that generated this memory"
    )
    related_memories: list[str] = Field(
        default_factory=list, description="IDs of related memories"
    )
    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Confidence in this memory"
    )
    observation_count: int = Field(
        default=1, description="How many times this pattern was observed"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_persistent: bool = Field(
        default=False, description="Whether to save across runs"
    )


class ExplorationReport(BaseModel):
    """Final report from an exploration run."""

    run_id: str = Field(..., description="ID of the research run")
    exploration_area: ExplorationArea = Field(...)
    ideas_explored: int = Field(..., description="Number of ideas explored")
    ideas_blocked: int = Field(..., description="Number of ideas blocked")
    total_findings: int = Field(..., description="Total findings discovered")
    total_memories: int = Field(..., description="Total memories created")
    per_idea_findings: dict[str, list[Finding]] = Field(
        default_factory=dict, description="Findings grouped by idea"
    )
    emergent_patterns: list[Memory] = Field(
        default_factory=list, description="High-level patterns identified"
    )
    open_questions: list[str] = Field(
        default_factory=list, description="Unanswered questions for future exploration"
    )
    not_explored: list[str] = Field(
        default_factory=list, description="Ideas or areas not explored"
    )
    tool_statistics: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool execution statistics (calls, time, success rate)",
    )
    duration_seconds: float = Field(
        default=0.0, description="Total run duration"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchRun(BaseModel):
    """One complete exploration session."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique run ID")
    area: ExplorationArea = Field(..., description="Exploration area scope")
    ideas: list[ExploratoryIdea] = Field(
        default_factory=list, description="All ideas in this run"
    )
    findings: list[Finding] = Field(
        default_factory=list, description="All findings in this run"
    )
    memories: list[Memory] = Field(
        default_factory=list, description="All memories in this run"
    )
    tool_traces: list[ToolTrace] = Field(
        default_factory=list, description="All tool execution traces"
    )
    status: RunStatus = Field(default=RunStatus.CREATED, description="Current run status")
    user_seed_ideas: Optional[list[str]] = Field(
        default=None, description="User-provided seed ideas"
    )
    # Budget tracking
    max_ideas: int = Field(default=20, description="Max exploratory ideas cap")
    max_tokens: int = Field(default=100000, description="Max LLM tokens budget")
    max_tool_calls: int = Field(default=200, description="Max tool calls budget")
    max_wall_clock_seconds: int = Field(
        default=3600, description="Max runtime in seconds (1 hour default)"
    )
    # Budget consumed
    tokens_used: int = Field(default=0)
    tool_calls_used: int = Field(default=0)
    wall_clock_used: int = Field(default=0)
    # Batch tracking
    current_batch_number: int = Field(default=0, description="Current batch in progress")
    batch_cursor: Optional[str] = Field(
        default=None, description="Cursor for resuming batch"
    )
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    # Configuration
    llm_provider: str = Field(default="claude", description="Which LLM provider to use")
    llm_model: Optional[str] = Field(default=None, description="Specific model to use")

    def is_budget_exhausted(self) -> bool:
        """Check if any budget limit is reached."""
        if self.tokens_used >= self.max_tokens:
            return True
        if self.tool_calls_used >= self.max_tool_calls:
            return True
        if self.wall_clock_used >= self.max_wall_clock_seconds:
            return True
        return False

    def remaining_budget(self) -> dict[str, int]:
        """Return remaining budget for each resource."""
        return {
            "tokens": max(0, self.max_tokens - self.tokens_used),
            "tool_calls": max(0, self.max_tool_calls - self.tool_calls_used),
            "wall_clock": max(0, self.max_wall_clock_seconds - self.wall_clock_used),
            "ideas": max(0, self.max_ideas - len(self.ideas)),
        }

    def idea_by_id(self, idea_id: str) -> Optional[ExploratoryIdea]:
        """Find an idea by ID."""
        return next((i for i in self.ideas if i.id == idea_id), None)

    def findings_for_idea(self, idea_id: str) -> list[Finding]:
        """Get all findings for a specific idea."""
        return [f for f in self.findings if f.idea_id == idea_id]
