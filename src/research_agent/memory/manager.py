"""Memory system for learning and knowledge retention across runs."""

import logging
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from collections import defaultdict

from research_agent.core.models import (
    Memory,
    MemoryType,
    ResearchRun,
)
from research_agent.core.config import settings

logger = logging.getLogger(__name__)


class MemoryIndex:
    """
    In-memory index for fast lookup and querying of learned memories.
    
    Supports:
    - Fast retrieval by type, source idea, and confidence
    - Deduplication and similarity detection
    - Persistent storage checkpoint
    - Query-based retrieval
    """

    def __init__(self, run_id: str):
        """Initialize memory index for a research run."""
        self.run_id = run_id
        self.memories: Dict[str, Memory] = {}  # id -> Memory
        self.by_type: Dict[MemoryType, List[str]] = defaultdict(list)  # type -> [memory_ids]
        self.by_source: Dict[str, List[str]] = defaultdict(list)  # idea_id -> [memory_ids]
        self.deduplicated_hashes: Set[str] = set()  # Track deduplicated memories
        
    def add_memory(self, memory: Memory, check_duplicate: bool = True) -> bool:
        """
        Add a memory to the index.
        
        Args:
            memory: Memory object to add
            check_duplicate: Whether to check for duplicates before adding
            
        Returns:
            True if added, False if duplicate/skipped
        """
        if check_duplicate and self._is_duplicate(memory):
            text = memory.summary + (memory.description or "")
            logger.debug(f"Skipping duplicate memory: {text[:50]}")
            return False
        
        # Store in index
        self.memories[memory.id] = memory
        self.by_type[memory.memory_type].append(memory.id)
        for idea_id in memory.related_ideas:
            if idea_id not in self.by_source:
                self.by_source[idea_id] = []
            self.by_source[idea_id].append(memory.id)
        
        text = memory.summary + (memory.description or "")
        logger.debug(f"Added memory: {text[:50]}")
        return True
    
    def query(
        self,
        memory_types: Optional[List[MemoryType]] = None,
        idea_id: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> List[Memory]:
        """
        Query memories from the index.
        
        Args:
            memory_types: Filter by memory types
            idea_id: Filter by source idea
            min_confidence: Minimum confidence threshold
            limit: Maximum results to return
            
        Returns:
            List of matching Memory objects
        """
        candidates = []
        
        if idea_id:
            # Query by source idea
            memory_ids = self.by_source.get(idea_id, [])
            candidates = [self.memories[mid] for mid in memory_ids if mid in self.memories]
        
        elif memory_types:
            # Query by type
            memory_ids = []
            for mtype in memory_types:
                memory_ids.extend(self.by_type.get(mtype, []))
            candidates = [self.memories[mid] for mid in memory_ids if mid in self.memories]
        
        else:
            # Return all
            candidates = list(self.memories.values())
        
        # Filter by confidence
        if min_confidence > 0:
            candidates = [m for m in candidates if m.confidence >= min_confidence]
        
        # Sort by confidence descending, then by recency
        candidates.sort(key=lambda m: (-m.confidence, -m.created_at.timestamp()))
        
        return candidates[:limit]
    
    def consolidate(self) -> None:
        """Consolidate memories: deduplicate, merge similar ones."""
        logger.info(f"Consolidating {len(self.memories)} memories")
        
        # Already tracking duplicates; could enhance with similarity clustering
        # For now, just log consolidation
        unique_count = len(self.memories)
        logger.info(f"Consolidated to {unique_count} unique memories")
    
    def list_all(self) -> List[Memory]:
        """Return all memories in the index."""
        return list(self.memories.values())
    
    def _is_duplicate(self, memory: Memory) -> bool:
        """Check if memory is a likely duplicate based on summary."""
        text = memory.summary + (memory.description or "")
        desc_hash = hash(text[:100])
        if desc_hash in self.deduplicated_hashes:
            return True
        
        self.deduplicated_hashes.add(desc_hash)
        return False


class MemoryLearner:
    """
    Extracts and synthesizes learnings from exploration activities.
    
    Handles:
    - Micro-learning from tool traces
    - Idea-level synthesis
    - Run-level consolidation
    """

    def __init__(self, memory_index: MemoryIndex):
        """Initialize learner with reference to memory index."""
        self.memory_index = memory_index
        self.learning_history: List[Dict[str, Any]] = []
    
    def extract_pattern_from_results(
        self,
        tool_name: str,
        tool_output: str,
        idea_description: str,
    ) -> Optional[Memory]:
        """
        Extract a pattern from tool results.
        
        Args:
            tool_name: Name of tool that ran
            tool_output: Output from the tool
            idea_description: What idea was being explored
            
        Returns:
            Memory object if pattern found, None otherwise
        """
        logger.debug(f"Extracting pattern from {tool_name} output")
        
        # Simple heuristics for common patterns
        patterns = []
        
        if tool_name == "search":
            # Count matches -> usage pattern
            lines = tool_output.split("\n")
            if "matches" in tool_output.lower():
                patterns.append(
                    f"High usage pattern found in {idea_description}"
                )
        
        if tool_name == "read":
            # Detect imports, class definitions, patterns
            if "class " in tool_output:
                patterns.append(
                    "Object-oriented design pattern detected"
                )
            if "import " in tool_output or "from " in tool_output:
                patterns.append(
                    "Module/package dependency structure evident"
                )
            if "async " in tool_output or "await " in tool_output:
                patterns.append(
                    "Asynchronous/concurrent pattern in use"
                )
        
        if patterns:
            memory = Memory(
                memory_type=MemoryType.PATTERN,
                description=patterns[0],
                confidence=0.6,  # Moderate confidence from heuristic detection
                persist=False,
            )
            logger.debug(f"Extracted pattern: {memory.description}")
            return memory
        
        return None
    
    def synthesize_idea_learnings(
        self,
        idea_title: str,
        observations: List[str],
    ) -> List[Memory]:
        """
        Synthesize idea-level learnings from multiple observations.
        
        Args:
            idea_title: Title of idea being explored
            observations: List of observations/findings
            
        Returns:
            List of synthesized Memory objects
        """
        if not observations:
            return []
        
        logger.debug(f"Synthesizing learnings from {len(observations)} observations")
        
        memories = []
        
        # If multiple observations, create a connection memory
        if len(observations) > 1:
            connection_desc = f"{idea_title}: {', '.join([o[:30] for o in observations[:3]])}"
            connection = Memory(
                memory_type=MemoryType.CONNECTION,
                description=connection_desc,
                confidence=0.7,
                persist=True,
            )
            memories.append(connection)
        
        # Create domain memory if patterns suggest domain knowledge
        if any("architecture" in o.lower() or "design" in o.lower() for o in observations):
            domain = Memory(
                memory_type=MemoryType.DOMAIN,
                description=f"Domain insight: {idea_title}",
                confidence=0.5,
                persist=True,
            )
            memories.append(domain)
        
        return memories
    
    def create_tool_signal_memory(
        self,
        tool_name: str,
        success: bool,
        output_preview: str,
    ) -> Memory:
        """
        Create a memory recording tool effectiveness.
        
        Args:
            tool_name: Name of the tool
            success: Whether tool succeeded
            output_preview: Preview of output
            
        Returns:
            ToolSignal memory
        """
        signal_text = (
            f"{tool_name} ({'successful' if success else 'failed'}): "
            f"{output_preview[:50]}"
        )
        
        return Memory(
            memory_type=MemoryType.TOOSIGNAL,
            description=signal_text,
            confidence=1.0 if success else 0.3,
            persist=False,
        )


class MemoryManager:
    """
    High-level manager for memory operations during a research run.
    
    Coordinates:
    - Memory indexing
    - Learning extraction
    - Persistence to storage
    """

    def __init__(self, run_id: str):
        """Initialize memory manager for a research run."""
        self.run_id = run_id
        self.index = MemoryIndex(run_id)
        self.learner = MemoryLearner(self.index)
    
    def record_learning(self, memory: Memory) -> bool:
        """
        Record a new learning in memory.
        
        Args:
            memory: Memory to record
            
        Returns:
            True if recorded, False if duplicate
        """
        return self.index.add_memory(memory)
    
    def search_memories(
        self,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 10,
    ) -> List[Memory]:
        """
        Search for relevant memories.
        
        Args:
            memory_types: Types of memories to search for
            limit: Maximum results
            
        Returns:
            List of matching memories
        """
        return self.index.query(memory_types=memory_types, limit=limit)
    
    def get_run_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all learnings from this run.
        
        Returns:
            Dictionary with memory statistics and key insights
        """
        all_memories = self.index.list_all()
        
        summary = {
            "total_memories": len(all_memories),
            "by_type": {},
            "high_confidence": [],
        }
        
        # Group by type
        for mtype in MemoryType:
            mtype_memories = [m for m in all_memories if m.memory_type == mtype]
            summary["by_type"][mtype.name] = len(mtype_memories)
        
        # Get high-confidence memories
        high_conf = sorted(
            all_memories,
            key=lambda m: -m.confidence
        )[:5]
        summary["high_confidence"] = [m.description for m in high_conf]
        
        return summary
    
    def checkpoint(self) -> Dict[str, Any]:
        """
        Create a checkpoint of current memories for persistence.
        
        Returns:
            Dictionary with memories serialized for storage
        """
        memories = self.index.list_all()
        return {
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "memories": [
                {
                    "id": m.id,
                    "type": m.memory_type.name,
                    "description": m.description,
                    "confidence": m.confidence,
                    "persist": m.persist,
                }
                for m in memories
            ],
        }
