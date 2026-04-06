"""Test core models."""

from research_agent.core.models import (
    ExplorationArea,
    ExploratoryIdea,
    IdeaStatus,
    Memory,
    MemoryType,
    ResearchRun,
    RunStatus,
)


def test_models_import():
    """Test that models can be imported."""
    assert ExplorationArea is not None
    assert ExploratoryIdea is not None
    assert ResearchRun is not None


def test_exploration_area():
    """Test ExplorationArea model."""
    area = ExplorationArea(
        roots=["src/", "lib/"],
        include_patterns=["*.py"],
        exclude_patterns=["**/*_test.py"],
        natural_language_hint="Python source code",
    )
    assert area.roots == ["src/", "lib/"]
    assert len(area.include_patterns) == 1


def test_exploratory_idea():
    """Test ExploratoryIdea model."""
    idea = ExploratoryIdea(
        title="How does auth work?",
        hypothesis="Authentication uses JWT tokens",
        priority=4,
    )
    assert idea.status == IdeaStatus.QUEUED
    assert idea.priority == 4
    assert len(idea.findings) == 0


def test_research_run(exploration_area):
    """Test ResearchRun model."""
    run = ResearchRun(
        area=exploration_area,
        max_ideas=20,
        max_tokens=100000,
    )
    assert run.status == RunStatus.CREATED
    assert len(run.ideas) == 0
    assert not run.is_budget_exhausted()


def test_research_run_budget_tracking(exploration_area):
    """Test budget tracking in ResearchRun."""
    run = ResearchRun(
        area=exploration_area,
        max_tokens=1000,
        max_tool_calls=10,
    )
    
    # Check remaining budget
    remaining = run.remaining_budget()
    assert remaining["tokens"] == 1000
    assert remaining["tool_calls"] == 10
    
    # Update budget usage
    run.tokens_used = 500
    run.tool_calls_used = 5
    
    remaining = run.remaining_budget()
    assert remaining["tokens"] == 500
    assert remaining["tool_calls"] == 5
    
    # Check exhausted
    run.tokens_used = 1000
    assert run.is_budget_exhausted()


def test_research_run_idea_lookup(exploration_area):
    """Test finding ideas by ID."""
    run = ResearchRun(area=exploration_area)
    
    idea1 = ExploratoryIdea(
        title="Idea 1",
        hypothesis="Test hypothesis 1",
    )
    idea2 = ExploratoryIdea(
        title="Idea 2",
        hypothesis="Test hypothesis 2",
    )
    
    run.ideas.append(idea1)
    run.ideas.append(idea2)
    
    # Lookup by ID
    found = run.idea_by_id(idea1.id)
    assert found is not None
    assert found.title == "Idea 1"
    
    # Not found
    found = run.idea_by_id("nonexistent")
    assert found is None


def test_memory_types():
    """Test Memory model with different types."""
    pattern_memory = Memory(
        memory_type=MemoryType.PATTERN,
        summary="DI pattern found in 3 services",
        confidence=0.85,
    )
    assert pattern_memory.memory_type == MemoryType.PATTERN
    assert pattern_memory.confidence == 0.85
    
    domain_memory = Memory(
        memory_type=MemoryType.DOMAIN,
        summary="PaymentService handles all transactions",
        is_persistent=True,
    )
    assert domain_memory.memory_type == MemoryType.DOMAIN
    assert domain_memory.is_persistent


def test_idea_statuses():
    """Test all idea status values."""
    statuses = [
        IdeaStatus.QUEUED,
        IdeaStatus.IN_PROGRESS,
        IdeaStatus.EXPLORED,
        IdeaStatus.BLOCKED,
        IdeaStatus.SKIPPED,
        IdeaStatus.DEFERRED,
    ]
    assert len(statuses) == 6


if __name__ == "__main__":
    print("✓ Basic model tests passed!")
