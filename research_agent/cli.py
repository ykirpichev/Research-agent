from __future__ import annotations

import argparse
from pathlib import Path

from research_agent.json_store import load_run, save_run
from research_agent.llm import llm_from_env
from research_agent.models import RunConfig
from research_agent.orchestrator import Orchestrator


def main() -> None:
    p = argparse.ArgumentParser(description="Sandboxed LLM code exploration agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start", help="Create a new research run")
    start.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root")
    start.add_argument(
        "--area",
        action="append",
        default=[],
        help="Exploration root relative to repo (repeatable). Default: .",
    )
    start.add_argument("--hint", default=None, help="Natural-language scope hint")
    start.add_argument("--guidance", default=None, help="Optional user guidance for ideas")
    start.add_argument(
        "--seed-idea",
        action="append",
        default=[],
        metavar="TITLE=HYPOTHESIS",
        help="Guided mode: seed idea (repeatable)",
    )
    start.add_argument("--max-ideas", type=int, default=20)
    start.add_argument("--state", type=Path, required=True, help="Write run JSON here")

    batch = sub.add_parser("batch", help="Execute one batch on a saved run")
    batch.add_argument("--state", type=Path, required=True)

    resume = sub.add_parser("resume", help="Run batches until completion")
    resume.add_argument("--state", type=Path, required=True)
    resume.add_argument("--max-batches", type=int, default=50)

    report = sub.add_parser("report", help="Print markdown report from saved run")
    report.add_argument("--state", type=Path, required=True)

    args = p.parse_args()
    llm = llm_from_env()
    orch = Orchestrator(llm)

    if args.cmd == "start":
        seeds: list[tuple[str, str]] = []
        for s in args.seed_idea:
            if "=" not in s:
                seeds.append((s, s))
            else:
                a, b = s.split("=", 1)
                seeds.append((a.strip(), b.strip()))
        cfg = RunConfig(max_exploratory_ideas=args.max_ideas)
        roots = args.area if args.area else ["."]
        run = orch.start_run(
            args.repo.resolve(),
            roots,
            hint=args.hint,
            guidance=args.guidance,
            seed_ideas=seeds or None,
            config=cfg,
        )
        save_run(args.state, run)
        print(run.id)

    elif args.cmd == "batch":
        run = load_run(args.state)
        orch.run_batch(run)
        save_run(args.state, run)
        print(run.status.value)

    elif args.cmd == "resume":
        run = load_run(args.state)
        orch.run_until_done(run, max_batches=args.max_batches)
        save_run(args.state, run)
        print(run.status.value)

    elif args.cmd == "report":
        run = load_run(args.state)
        rep = orch.build_report(run)
        print(rep.to_markdown())
