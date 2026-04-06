from pathlib import Path

from research_agent.llm import StubLLM
from research_agent.orchestrator import Orchestrator


def test_stub_run_completes(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text("x = 1\n")
    orch = Orchestrator(StubLLM())
    run = orch.start_run(tmp_path, ["src"], hint="test module")
    assert run.ideas
    orch.run_until_done(run, max_batches=5)
    assert run.status.value == "completed"
    rep = orch.build_report(run)
    assert rep.run_id == run.id
    assert "Exploration report" in rep.to_markdown()
