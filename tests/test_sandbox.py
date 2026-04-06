from pathlib import Path

import pytest

from research_agent.sandbox import PathSandbox


def test_path_traversal_rejected(tmp_path: Path) -> None:
    sb = PathSandbox(tmp_path, ["."], [])
    (tmp_path / "safe.txt").write_text("x")
    with pytest.raises(ValueError):
        sb.resolve_under_area("../outside")


def test_resolve_must_be_under_area(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    sb = PathSandbox(tmp_path, ["a"], [])
    (tmp_path / "a" / "f").write_text("ok")
    sb.resolve_under_area("a/f")
    with pytest.raises(ValueError):
        sb.resolve_under_area("b")
