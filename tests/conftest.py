"""Pytest configuration and fixtures."""

import tempfile
from pathlib import Path

import pytest

from research_agent.core.models import ExplorationArea, ResearchRun


@pytest.fixture
def temp_codebase(tmp_path) -> str:
    """Create a temporary codebase for testing."""
    # Create some mock files
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Create some Python files
    (src_dir / "main.py").write_text("""
def main():
    print("Hello, World!")
    
if __name__ == "__main__":
    main()
""")

    (src_dir / "auth.py").write_text("""
class AuthService:
    def authenticate(self, username: str, password: str) -> bool:
        return True
    
    def get_session(self, user_id: str):
        return {"user_id": user_id}
""")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("""
def test_main():
    assert True
""")

    return str(tmp_path)


@pytest.fixture
def exploration_area(temp_codebase) -> ExplorationArea:
    """Create a test exploration area."""
    return ExplorationArea(
        roots=[str(Path(temp_codebase) / "src")],
        include_patterns=["*.py"],
        natural_language_hint="Python source code",
    )


@pytest.fixture
def research_run(exploration_area) -> ResearchRun:
    """Create a test research run."""
    return ResearchRun(
        area=exploration_area,
        llm_provider="local/ollama",
        max_ideas=10,
        max_tokens=10000,
    )
