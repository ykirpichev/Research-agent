"""Integration tests for research agent components."""

from uuid import uuid4

from research_agent.core.models import Memory, MemoryType, ExploratoryIdea, IdeaStatus
from research_agent.core.orchestrator import ResearchOrchestrator
from research_agent.llm.wrapper import LLMWrapper
from research_agent.memory import MemoryManager, MemoryIndex


class TestComponentIntegration:
    """Test that core components integrate correctly."""

    def test_orchestrator_with_llm_wrapper(self, research_run):
        """Verify orchestrator and LLM wrapper can work together."""
        orchestrator = ResearchOrchestrator(research_run)
        wrapper = LLMWrapper()
        
        assert orchestrator.run is not None
        assert wrapper.reasoner_model is not None

    def test_memory_manager_basic_operations(self):
        """Verify memory manager can record and search memories."""
        manager = MemoryManager(str(uuid4()))
        
        memory = Memory(
            memory_type=MemoryType.PATTERN,
            summary="Test pattern discovery",
            confidence=0.7,
        )
        
        added = manager.record_learning(memory)
        assert added is True

    def test_memory_deduplication(self):
        """Verify memory system deduplicates identical memories."""
        manager = MemoryManager(str(uuid4()))
        
        memory1 = Memory(
            memory_type=MemoryType.PATTERN,
            summary="Factory pattern found",
            confidence=0.85,
        )
        memory2 = Memory(
            memory_type=MemoryType.PATTERN,
            summary="Factory pattern found",
            confidence=0.85,
        )
        
        result1 = manager.record_learning(memory1)
        result2 = manager.record_learning(memory2)
        
        assert result1 is True
        assert result2 is False  # Duplicate

    def test_orchestrator_idea_batch(self, research_run):
        """Verify orchestrator can retrieve idea batches."""
        orchestrator = ResearchOrchestrator(research_run)
        
        for i in range(5):
            idea = ExploratoryIdea(
                id=f"test-idea-{i}",
                title=f"Test Idea {i}",
                hypothesis=f"Test hypothesis {i}",
                status=IdeaStatus.QUEUED,
            )
            research_run.ideas.append(idea)
        
        batch = orchestrator._get_next_idea_batch()
        assert len(batch) > 0

    def test_llm_wrapper_methods_available(self):
        """Verify LLM wrapper has required methods."""
        wrapper = LLMWrapper()
        
        methods = [
            'generate_ideas',
            'plan_exploration',
            'synthesize_findings',
            'extract_learnings',
            'decide_next_action',
        ]
        
        for method_name in methods:
            assert hasattr(wrapper, method_name)
            assert callable(getattr(wrapper, method_name))

    def test_memory_index_operations(self):
        """Verify memory index can store and query memories."""
        index = MemoryIndex("test-run")
        
        memories = [
            Memory(memory_type=MemoryType.PATTERN, summary="Pattern 1"),
            Memory(memory_type=MemoryType.DOMAIN, summary="Domain 1"),
        ]
        
        for mem in memories:
            index.add_memory(mem)
        
        all_results = index.query()
        assert len(all_results) == 2

    def test_orchestrator_seed_generation(self, research_run):
        """Verify orchestrator generates seed ideas."""
        orchestrator = ResearchOrchestrator(research_run)
        ideas = orchestrator._generate_seed_ideas()
        
        assert len(ideas) > 0
        assert all(isinstance(i, ExploratoryIdea) for i in ideas)

    def test_api_imports(self):
        """Verify REST API can be imported."""
        from research_agent.api import app
        
        assert app is not None
        assert len(app.routes) > 0
