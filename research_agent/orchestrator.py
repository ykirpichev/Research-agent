from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from research_agent.llm import (
    LLMClient,
    build_batch_tool_prompt,
    build_idea_generation_prompt,
    build_synthesis_prompt,
    parse_idea_response,
    parse_synthesis,
    parse_tool_calls,
)
from research_agent.models import (
    ExplorationArea,
    ExplorationReport,
    ExploratoryIdea,
    Finding,
    IdeaStatus,
    ResearchRun,
    RunConfig,
    RunStatus,
    ToolTrace,
)
from research_agent.sandbox import PathSandbox
from research_agent.tools import CodeTools


class Orchestrator:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def start_run(
        self,
        repo_root: str | Path,
        area_roots: list[str],
        hint: str | None = None,
        exclude_globs: list[str] | None = None,
        guidance: str | None = None,
        seed_ideas: list[tuple[str, str]] | None = None,
        config: RunConfig | None = None,
    ) -> ResearchRun:
        cfg = config or RunConfig()
        area = ExplorationArea(
            root_paths=list(area_roots) if area_roots else ["."],
            hint=hint,
            exclude_globs=list(exclude_globs or []),
        )
        run = ResearchRun.new(str(Path(repo_root).resolve()), area, cfg, guidance=guidance)
        run.status = RunStatus.RUNNING

        if seed_ideas:
            for title, hyp in seed_ideas[: cfg.max_exploratory_ideas]:
                run.ideas.append(
                    ExploratoryIdea(
                        id=str(uuid4()),
                        title=title,
                        hypothesis=hyp,
                        priority=10,
                        status=IdeaStatus.QUEUED,
                    )
                )
        else:
            sys_p, usr_p = build_idea_generation_prompt(area, guidance, cfg.max_exploratory_ideas)
            raw = self._llm.complete(sys_p, usr_p)
            for item in parse_idea_response(raw, cfg.max_exploratory_ideas):
                run.ideas.append(
                    ExploratoryIdea(
                        id=str(uuid4()),
                        title=item["title"],
                        hypothesis=item["hypothesis"],
                        priority=item["priority"],
                        status=IdeaStatus.QUEUED,
                    )
                )

        if not run.ideas:
            run.ideas.append(
                ExploratoryIdea(
                    id=str(uuid4()),
                    title="Initial scan",
                    hypothesis="List top-level structure of the exploration area.",
                    priority=0,
                    status=IdeaStatus.QUEUED,
                )
            )

        run.touch()
        return run

    def run_batch(self, run: ResearchRun) -> ResearchRun:
        """Execute one batch: optional tool round + synthesis; may pause or complete."""
        if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
            return run

        repo = Path(run.repo_root)
        sb = PathSandbox(repo, run.area.root_paths, run.area.exclude_globs)
        tools = CodeTools(sb, run.config)

        pending = [i for i in run.ideas if i.status in (IdeaStatus.QUEUED, IdeaStatus.IN_PROGRESS)]
        for i in pending[:5]:
            if i.status == IdeaStatus.QUEUED:
                i.status = IdeaStatus.IN_PROGRESS

        batch_ideas = pending[:5] or run.ideas[:3]
        t_batch_start = time.monotonic()

        tool_round_json: list[dict] = []
        calls_in_batch = 0

        if time.monotonic() - t_batch_start <= run.config.batch_wall_seconds:
            sys_t, usr_t = build_batch_tool_prompt(run, batch_ideas)
            raw_tools = self._llm.complete(sys_t, usr_t)
            tool_calls, _notes = parse_tool_calls(raw_tools)
            for call in tool_calls:
                if calls_in_batch >= run.config.max_tool_calls_per_batch:
                    break
                if run.tool_calls_used >= run.config.max_tool_calls_total:
                    break
                if time.monotonic() - t_batch_start > run.config.batch_wall_seconds:
                    break

                name = call["tool"]
                args = call["args"]
                idea_ids = call["idea_ids"]
                t0 = time.perf_counter()
                result = tools.dispatch(name, args)
                dt_ms = (time.perf_counter() - t0) * 1000

                trace = ToolTrace(
                    id=str(uuid4()),
                    tool_name=name,
                    args_summary=json.dumps(args, sort_keys=True)[:500],
                    idea_ids=idea_ids,
                    duration_ms=dt_ms,
                    ok=result.ok,
                    stdout_excerpt=result.stdout[-2000:],
                    stderr_excerpt=result.stderr[-2000:],
                    structured_result=result.data,
                )
                run.traces.append(trace)
                run.tool_calls_used += 1
                calls_in_batch += 1
                tool_round_json.append(
                    {
                        "tool": name,
                        "args": args,
                        "ok": result.ok,
                        "data": result.data,
                        "stdout": result.stdout[-4000:],
                        "stderr": result.stderr[-4000:],
                    }
                )

        sys_s, usr_s = build_synthesis_prompt(run, json.dumps(tool_round_json, indent=2)[:120_000])
        raw_syn = self._llm.complete(sys_s, usr_s)
        try:
            syn = parse_synthesis(raw_syn)
        except json.JSONDecodeError:
            run.error_message = "synthesis JSON parse failed"
            run.status = RunStatus.FAILED
            run.touch()
            return run

        for f in syn.get("findings") or []:
            if not isinstance(f, dict):
                continue
            iid = f.get("idea_id")
            if not iid or not run.idea_by_id(str(iid)):
                continue
            run.findings.append(
                Finding(
                    idea_id=str(iid),
                    summary=str(f.get("summary", "")),
                    observed_vs_inferred=str(f.get("observed_vs_inferred") or "mixed"),
                    related_trace_ids=[],
                )
            )

        for u in syn.get("idea_status_updates") or []:
            if not isinstance(u, dict):
                continue
            idea = run.idea_by_id(str(u.get("id", "")))
            if not idea:
                continue
            st = u.get("status")
            if isinstance(st, str):
                try:
                    idea.status = IdeaStatus(st)
                except ValueError:
                    pass

        if isinstance(syn.get("global_themes"), str):
            run.synthesis_themes = syn["global_themes"]
        if isinstance(syn.get("open_questions"), str):
            run.synthesis_open_questions = syn["open_questions"]

        run.batch_index += 1
        done = bool(syn.get("done"))
        stalled = not tool_round_json and not done
        if stalled and not run.error_message:
            run.error_message = "No tool_calls planned; ending run."
        if done or stalled or run.tool_calls_used >= run.config.max_tool_calls_total:
            run.status = RunStatus.COMPLETED
            for i in run.ideas:
                if i.status == IdeaStatus.IN_PROGRESS:
                    i.status = IdeaStatus.EXPLORED
                if i.status == IdeaStatus.QUEUED:
                    i.status = IdeaStatus.SKIPPED
        else:
            run.status = RunStatus.PAUSED_BATCH

        run.touch()
        return run

    def run_until_done(self, run: ResearchRun, max_batches: int = 50) -> ResearchRun:
        n = 0
        while run.status not in (RunStatus.COMPLETED, RunStatus.FAILED) and n < max_batches:
            self.run_batch(run)
            n += 1
        if run.status == RunStatus.PAUSED_BATCH:
            run.status = RunStatus.COMPLETED
            run.touch()
        return run

    def build_report(self, run: ResearchRun) -> ExplorationReport:
        per: list[dict] = []
        for idea in run.ideas:
            fd = [f for f in run.findings if f.idea_id == idea.id]
            summary = fd[-1].summary if fd else ""
            per.append({"title": idea.title, "status": idea.status.value, "finding": summary})
        themes = run.synthesis_themes or ""
        open_q = run.synthesis_open_questions or ""
        lim = f"Stopped with status {run.status.value}; tool_calls_used={run.tool_calls_used}."
        if run.error_message:
            lim += f" Error: {run.error_message}"
        return ExplorationReport(
            run_id=run.id,
            global_themes=themes or "(no synthesis themes stored separately in v1)",
            open_questions=open_q or "(see LLM open_questions in future version)",
            per_idea=per,
            limitations=lim,
        )
