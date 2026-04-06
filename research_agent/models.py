from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IdeaStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    EXPLORED = "explored"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED_BATCH = "paused_batch"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExplorationArea:
    """User-defined scope inside the repository."""

    root_paths: list[str]  # relative to repo root, e.g. ["src/pkg"]
    hint: str | None = None
    exclude_globs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_paths": self.root_paths,
            "hint": self.hint,
            "exclude_globs": self.exclude_globs,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExplorationArea:
        return cls(
            root_paths=list(d["root_paths"]),
            hint=d.get("hint"),
            exclude_globs=list(d.get("exclude_globs") or []),
        )


@dataclass
class ExploratoryIdea:
    id: str
    title: str
    hypothesis: str
    priority: int = 0
    status: IdeaStatus = IdeaStatus.QUEUED
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "hypothesis": self.hypothesis,
            "priority": self.priority,
            "status": self.status.value,
            "parent_id": self.parent_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExploratoryIdea:
        return cls(
            id=d["id"],
            title=d["title"],
            hypothesis=d["hypothesis"],
            priority=int(d.get("priority") or 0),
            status=IdeaStatus(d["status"]),
            parent_id=d.get("parent_id"),
        )


@dataclass
class ToolTrace:
    id: str
    tool_name: str
    args_summary: str
    idea_ids: list[str]
    duration_ms: float
    ok: bool
    stdout_excerpt: str
    stderr_excerpt: str
    structured_result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "args_summary": self.args_summary,
            "idea_ids": self.idea_ids,
            "duration_ms": self.duration_ms,
            "ok": self.ok,
            "stdout_excerpt": self.stdout_excerpt,
            "stderr_excerpt": self.stderr_excerpt,
            "structured_result": self.structured_result,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolTrace:
        return cls(
            id=d["id"],
            tool_name=d["tool_name"],
            args_summary=d["args_summary"],
            idea_ids=list(d["idea_ids"]),
            duration_ms=float(d["duration_ms"]),
            ok=bool(d["ok"]),
            stdout_excerpt=d.get("stdout_excerpt") or "",
            stderr_excerpt=d.get("stderr_excerpt") or "",
            structured_result=d.get("structured_result"),
        )


@dataclass
class Finding:
    idea_id: str
    summary: str
    observed_vs_inferred: str = "mixed"
    related_trace_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "summary": self.summary,
            "observed_vs_inferred": self.observed_vs_inferred,
            "related_trace_ids": self.related_trace_ids,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Finding:
        return cls(
            idea_id=d["idea_id"],
            summary=d["summary"],
            observed_vs_inferred=d.get("observed_vs_inferred") or "mixed",
            related_trace_ids=list(d.get("related_trace_ids") or []),
        )


@dataclass
class RunConfig:
    max_exploratory_ideas: int = 20
    max_tool_calls_per_batch: int = 12
    max_tool_calls_total: int = 200
    batch_wall_seconds: float = 120.0
    read_file_max_lines: int = 400
    search_max_matches: int = 40

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_exploratory_ideas": self.max_exploratory_ideas,
            "max_tool_calls_per_batch": self.max_tool_calls_per_batch,
            "max_tool_calls_total": self.max_tool_calls_total,
            "batch_wall_seconds": self.batch_wall_seconds,
            "read_file_max_lines": self.read_file_max_lines,
            "search_max_matches": self.search_max_matches,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunConfig:
        return cls(
            max_exploratory_ideas=int(d.get("max_exploratory_ideas", 20)),
            max_tool_calls_per_batch=int(d.get("max_tool_calls_per_batch", 12)),
            max_tool_calls_total=int(d.get("max_tool_calls_total", 200)),
            batch_wall_seconds=float(d.get("batch_wall_seconds", 120.0)),
            read_file_max_lines=int(d.get("read_file_max_lines", 400)),
            search_max_matches=int(d.get("search_max_matches", 40)),
        )


@dataclass
class ResearchRun:
    id: str
    repo_root: str
    area: ExplorationArea
    config: RunConfig
    status: RunStatus = RunStatus.PENDING
    ideas: list[ExploratoryIdea] = field(default_factory=list)
    traces: list[ToolTrace] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    guidance: str | None = None
    batch_index: int = 0
    tool_calls_used: int = 0
    error_message: str | None = None
    synthesis_themes: str | None = None
    synthesis_open_questions: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def touch(self) -> None:
        self.updated_at = _utc_now()

    def idea_by_id(self, idea_id: str) -> ExploratoryIdea | None:
        for i in self.ideas:
            if i.id == idea_id:
                return i
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repo_root": self.repo_root,
            "area": self.area.to_dict(),
            "config": self.config.to_dict(),
            "status": self.status.value,
            "ideas": [i.to_dict() for i in self.ideas],
            "traces": [t.to_dict() for t in self.traces],
            "findings": [f.to_dict() for f in self.findings],
            "guidance": self.guidance,
            "batch_index": self.batch_index,
            "tool_calls_used": self.tool_calls_used,
            "error_message": self.error_message,
            "synthesis_themes": self.synthesis_themes,
            "synthesis_open_questions": self.synthesis_open_questions,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ResearchRun:
        return cls(
            id=d["id"],
            repo_root=d["repo_root"],
            area=ExplorationArea.from_dict(d["area"]),
            config=RunConfig.from_dict(d["config"]),
            status=RunStatus(d["status"]),
            ideas=[ExploratoryIdea.from_dict(x) for x in d.get("ideas") or []],
            traces=[ToolTrace.from_dict(x) for x in d.get("traces") or []],
            findings=[Finding.from_dict(x) for x in d.get("findings") or []],
            guidance=d.get("guidance"),
            batch_index=int(d.get("batch_index") or 0),
            tool_calls_used=int(d.get("tool_calls_used") or 0),
            error_message=d.get("error_message"),
            synthesis_themes=d.get("synthesis_themes"),
            synthesis_open_questions=d.get("synthesis_open_questions"),
            created_at=datetime.fromisoformat(d["created_at"]),
            updated_at=datetime.fromisoformat(d["updated_at"]),
        )

    @classmethod
    def new(
        cls,
        repo_root: str,
        area: ExplorationArea,
        config: RunConfig | None = None,
        guidance: str | None = None,
    ) -> ResearchRun:
        return cls(
            id=str(uuid4()),
            repo_root=repo_root,
            area=area,
            config=config or RunConfig(),
            guidance=guidance,
        )


@dataclass
class ExplorationReport:
    run_id: str
    global_themes: str
    open_questions: str
    per_idea: list[dict[str, Any]]
    limitations: str

    def to_markdown(self) -> str:
        lines = [
            f"# Exploration report (`{self.run_id}`)",
            "",
            "## Themes",
            self.global_themes,
            "",
            "## Per idea",
        ]
        for block in self.per_idea:
            lines.append(f"### {block.get('title', '?')}")
            lines.append(f"**Status:** {block.get('status', '?')}")
            lines.append("")
            lines.append(block.get("finding", "(no finding yet)"))
            lines.append("")
        lines.extend(["## Open questions", self.open_questions, "", "## Limitations", self.limitations])
        return "\n".join(lines)
