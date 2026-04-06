from __future__ import annotations

import json
from pathlib import Path

from research_agent.models import ResearchRun


def save_run(path: Path, run: ResearchRun) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run.to_dict(), indent=2), encoding="utf-8")


def load_run(path: Path) -> ResearchRun:
    return ResearchRun.from_dict(json.loads(path.read_text(encoding="utf-8")))
