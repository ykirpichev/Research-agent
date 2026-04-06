from pathlib import Path

from research_agent.models import RunConfig
from research_agent.sandbox import PathSandbox
from research_agent.tools import CodeTools


def test_find_and_read(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "foo.py").write_text("def hello():\n    return 42\n")
    sb = PathSandbox(tmp_path, ["pkg"], [])
    tools = CodeTools(sb, RunConfig())
    r = tools.find_in_codebase(r"def\s+hello")
    assert r.ok
    assert r.data["matches"]
    path = r.data["matches"][0]["path"]
    r2 = tools.read_file_range(path, 1, 5)
    assert r2.ok
    assert "def hello" in r2.data["content"]
