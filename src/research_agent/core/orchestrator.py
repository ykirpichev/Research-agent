"""Orchestrator for research exploration loop: Reason → Act → Learn → Memorize."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import field, dataclass

from research_agent.core.models import (
    ResearchRun,
    ExplorationArea,
    ExploratoryIdea,
    IdeaStatus,
    Finding,
    Memory,
    MemoryType,
    ToolTrace,
)
from research_agent.core.config import settings
from research_agent.tools.sandbox import SandboxError, PermissionError as SandboxPermissionError

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationContext:
    """Context for a single orchestration cycle."""

    run: ResearchRun
    current_batch: List[ExploratoryIdea] = field(default_factory=list)
    cycle_number: int = 0
    tool_traces_in_cycle: List[ToolTrace] = field(default_factory=list)
    memories_created: List[Memory] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)


class ResearchOrchestrator:
    """
    Orchestrates the Reason → Act → Learn → Memorize cycle for code exploration.
    
    Manages:
    - Idea generation and prioritization (Reason phase)
    - Tool execution planning and execution (Act phase)
    - Continuous learning from tool traces (Learn phases 1-3)
    - Memory consolidation and persistence (Memorize phase)
    - Budget tracking and run completion
    """

    def __init__(self, run: ResearchRun, llm_wrapper: Optional[Any] = None):
        """
        Initialize orchestrator for a research run.
        
        Args:
            run: ResearchRun instance to manage
            llm_wrapper: LLM wrapper for generation/synthesis (optional, will use stub)
        """
        self.run = run
        self.llm_wrapper = llm_wrapper  # Will be injected by LLM integration
        self.cycle_count = 0
        self.context: Optional[OrchestrationContext] = None
        
    async def execute_exploration(self) -> ResearchRun:
        """
        Execute the full exploration loop until completion or budget exhaustion.
        
        Returns:
            The completed ResearchRun with findings and memories.
        """
        logger.info(f"Starting exploration of {self.run.area.roots}")
        
        try:
            while not self._is_run_complete():
                await self._execute_orchestration_cycle()
                self.cycle_count += 1
                
                # Safety: never exceed reasonable limits
                if self.cycle_count > 100:
                    logger.warning("Safety limit reached: cycle_count > 100, stopping exploration")
                    self.run.status = "safety_limit_reached"
                    break
                    
        except Exception as e:
            logger.error(f"Error during exploration: {e}", exc_info=True)
            self.run.status = "error"
            self.run.error_message = str(e)
        
        # Finalization: synthesize run-level learnings
        await self._finalize_run()
        
        return self.run
    
    async def _execute_orchestration_cycle(self) -> None:
        """Execute a single cycle: Reason → Act → Learn → Memorize."""
        self.context = OrchestrationContext(
            run=self.run,
            cycle_number=self.cycle_count,
            start_time=datetime.now(),
        )
        
        logger.info(f"Cycle {self.cycle_count}: Starting orchestration cycle")
        
        # Phase 1: REASON — Generate & Prioritize Ideas
        await self._reason_phase()
        
        # Phase 2: ACT — Plan & Execute
        await self._act_phase()
        
        # Phase 3: LEARN — Continuous learning during Act, then synthesis
        await self._learn_phase()
        
        # Phase 4: MEMORIZE — Consolidate & Persist
        await self._memorize_phase()
        
        # Check budgets
        if self.run.is_budget_exhausted():
            logger.info("Budget exhausted, stopping exploration")
            self.run.status = "budget_exhausted"
    
    async def _reason_phase(self) -> None:
        """
        Phase 1: REASON — Generate and prioritize exploratory ideas.
        
        - Check if we have capacity for more ideas
        - Query memory index for context
        - Call LLM to generate new ideas
        - Prioritize and enqueue ideas
        """
        # Check capacity
        if len(self.run.ideas) >= settings.research.max_ideas:
            logger.debug(f"Already at max ideas ({len(self.run.ideas)}), skipping generation")
            return
        
        # Check if queue is empty
        queued_ideas = [i for i in self.run.ideas if i.status == IdeaStatus.QUEUED]
        if queued_ideas:
            logger.debug(f"Idea queue not empty ({len(queued_ideas)} queued), skipping generation")
            return
        
        logger.info("Reason phase: Generating new ideas")
        
        # TODO: Query memory index for context (requires memory system)
        memory_context: Dict[str, Any] = {}
        
        # Call LLM to generate ideas
        if self.llm_wrapper:
            exploration_context = f"Explore codebase in {self.run.area.roots}"
            new_ideas = await self.llm_wrapper.generate_ideas(
                exploration_context=exploration_context,
                prior_findings=self.run.all_findings,
                memory_context=memory_context,
                max_to_generate=max_to_generate,
            )
        else:
            # Fallback: generate simple seed ideas
            new_ideas = self._generate_seed_ideas()
        
        if new_ideas:
            self.run.ideas.extend(new_ideas)
            logger.info(f"Generated {len(new_ideas)} new ideas")
            
            # Track token usage for generation
            self.run.track_tokens_used(len(new_ideas) * 100)  # Estimate: ~100 tokens per idea
    
    async def _act_phase(self) -> None:
        """
        Phase 2: ACT — Plan and execute tool calls for ideas.
        
        - Get next batch of ideas to explore
        - Call LLM to plan tool calls
        - Execute tools in sandbox
        - Track traces
        """
        logger.info("Act phase: Planning and executing tools")
        
        # Get next batch
        self.context.current_batch = self._get_next_idea_batch()
        if not self.context.current_batch:
            logger.debug("No ideas in queue for act phase")
            return
        
        logger.info(f"Processing {len(self.context.current_batch)} ideas")
        
        # Call LLM to plan tool calls for batch (requires LLM wrapper)
        if self.llm_wrapper:
            tool_calls = await self.llm_wrapper.plan_exploration(
                ideas=self.context.current_batch,
                prior_tool_traces=self.run.tool_traces,
                remaining_budget={
                    "token_budget": self.run.remaining_tokens,
                    "tool_call_budget": self.run.remaining_tool_calls,
                    "wall_clock_budget": self.run.remaining_time.total_seconds() if self.run.remaining_time else None,
                },
            )
        else:
            # Fallback: generate simple tool calls
            tool_calls = self._generate_tool_calls_for_batch(self.context.current_batch)
        
        # Execute tools
        for tool_call in tool_calls:
            try:
                trace = await self._execute_tool(tool_call)
                self.context.tool_traces_in_cycle.append(trace)
                self.run.tool_traces.append(trace)
                
                # Mark idea as in progress
                if tool_call["idea_id"]:
                    idea = self.run.idea_by_id(tool_call["idea_id"])
                    if idea:
                        idea.status = IdeaStatus.IN_PROGRESS
                        
            except SandboxError as e:
                logger.warning(f"Sandbox error executing tool: {e}")
            except Exception as e:
                logger.error(f"Error executing tool: {e}", exc_info=True)
    
    async def _learn_phase(self) -> None:
        """
        Phase 3: LEARN — Extract learnings from execution and synthesize.
        
        Micro-learning:
        - Extract signals from each tool trace
        
        Idea-level learning:
        - Synthesize findings for each idea in batch
        - Extract connections and patterns
        """
        logger.info("Learn phase: Extracting learnings from tool traces")
        
        # Micro-learning: Extract from each trace
        for trace in self.context.tool_traces_in_cycle:
            if trace.success and self.llm_wrapper:
                micro_memories = await self.llm_wrapper.extract_learnings(
                    tool_trace=trace,
                    idea=self.run.idea_by_id(trace.idea_id) if trace.idea_id else None,
                    existing_patterns=[],  # TODO: pass existing patterns
                )
                self.context.memories_created.extend(micro_memories)
        
        logger.info(f"Extracted {len(self.context.memories_created)} micro-learnings")
        
        # Idea-level learning: Synthesize per idea
        for idea in self.context.current_batch:
            idea_traces = [t for t in self.context.tool_traces_in_cycle 
                          if t.idea_id == idea.id]
            if not idea_traces:
                continue
            
            # Call LLM to synthesize findings
            if self.llm_wrapper:
                findings = await self.llm_wrapper.synthesize_findings(
                    idea=idea,
                    tool_traces=idea_traces,
                    prior_findings=idea.findings,
                )
            else:
                findings = self._synthesize_findings_for_idea(idea, idea_traces)
            if findings:
                idea.findings.extend(findings)
                logger.debug(f"Synthesized {len(findings)} findings for idea {idea.id}")
            
            # Extract idea-level memories
            if self.llm_wrapper:
                idea_memories = await self.llm_wrapper.extract_learnings(
                    tool_trace=idea_traces[0],  # Use first trace as representative
                    idea=idea,
                    existing_patterns=[],  # TODO: pass existing patterns
                )
                self.context.memories_created.extend(idea_memories)
            
            # Decide next action for idea
            if self.llm_wrapper:
                next_action = await self.llm_wrapper.decide_next_action(idea, idea.findings)
            else:
                next_action = self._decide_next_action_for_idea(idea)
            self._apply_decision(idea, next_action)
    
    async def _memorize_phase(self) -> None:
        """
        Phase 4: MEMORIZE — Consolidate and persist learnings.
        
        - Deduplicate memories
        - Persist to storage
        - Update memory index
        """
        logger.info(f"Memorize phase: Consolidating {len(self.context.memories_created)} memories")
        
        # TODO: Add to memory index (requires memory system)
        # For now, just add directly to run
        for memory in self.context.memories_created:
            memory.created_at = datetime.now()
            # TODO: Check for duplicates and mark as persistent
        
        logger.info("Memories consolidated and persisted")
    
    async def _finalize_run(self) -> None:
        """Finalize the run: synthesize all learnings and generate report."""
        logger.info("Finalizing exploration run")
        
        # TODO: Call LLM to synthesize run-level learnings
        # TODO: Generate exploration report
        # TODO: Persist final state to database
        
        self.run.completed_at = datetime.now()
        self.run.status = "completed"
        logger.info(f"Exploration completed in {self.cycle_count} cycles")
    
    # ========== Phase Subtasks ==========
    
    def _get_next_idea_batch(self) -> List[ExploratoryIdea]:
        """Get next batch of ideas to explore."""
        queued = [i for i in self.run.ideas if i.status == IdeaStatus.QUEUED]
        return queued[:settings.research.batch_size]
    
    def _generate_seed_ideas(self) -> List[ExploratoryIdea]:
        """Generate initial seed ideas from exploration area."""
        ideas = []
        
        # Start with user-provided seed ideas
        for idx, seed in enumerate(self.run.user_seed_ideas or []):
            idea = ExploratoryIdea(
                id=f"seed-{idx}",
                title=seed,
                description=f"User-provided seed idea: {seed}",
                exploration_area=self.run.area,
                parent_id=None,
                priority=5,  # High priority for user seeds
            )
            ideas.append(idea)
        
        # If no seed ideas, generate default ones based on exploration area
        if not ideas:
            default_ideas = [
                "Identify main entry point(s)",
                "Understand project structure and organization",
                "Find key design patterns and architectural style",
                "Identify configuration and secrets handling",
                "Explore authentication and authorization",
            ]
            
            for idx, title in enumerate(default_ideas[:3]):  # Start with first 3
                idea = ExploratoryIdea(
                    id=f"default-{idx}",
                    title=title,
                    description=title,
                    exploration_area=self.run.area,
                    parent_id=None,
                    priority=3,
                )
                ideas.append(idea)
        
        return ideas
    
    def _generate_tool_calls_for_batch(self, ideas: List[ExploratoryIdea]) -> List[Dict[str, Any]]:
        """Generate tool calls for a batch of ideas."""
        tool_calls = []
        
        for idea in ideas:
            # Determine tools to call based on idea title
            if "entry" in idea.title.lower():
                # Search for main, __main__, etc.
                tool_calls.append({
                    "type": "search",
                    "idea_id": idea.id,
                    "pattern": r"def main|if __name__|def run|def start",
                    "description": f"Find entry point for idea: {idea.title}",
                })
            
            if "structure" in idea.title.lower():
                # List the directory structure
                tool_calls.append({
                    "type": "list",
                    "idea_id": idea.id,
                    "path": str(self.run.area.roots[0]) if self.run.area.roots else ".",
                    "max_depth": 3,
                    "description": f"Explore project structure for idea: {idea.title}",
                })
            
            if "pattern" in idea.title.lower() or "style" in idea.title.lower():
                # Search for common patterns
                tool_calls.append({
                    "type": "search",
                    "idea_id": idea.id,
                    "pattern": r"class|def|async def",
                    "max_results": 20,
                    "description": f"Find design patterns for idea: {idea.title}",
                })
        
        if not tool_calls:
            # Default: list root and search for Python files
            if ideas:
                tool_calls.append({
                    "type": "list",
                    "idea_id": ideas[0].id,
                    "path": str(self.run.area.roots[0]) if self.run.area.roots else ".",
                    "max_depth": 2,
                    "description": "Initial exploration of codebase structure",
                })
        
        return tool_calls
    
    async def _execute_tool(self, tool_call: Dict[str, Any]) -> ToolTrace:
        """
        Execute a single tool call and return trace.
        
        Args:
            tool_call: Tool call specification
            
        Returns:
            ToolTrace with execution results
        """
        # TODO: Implement actual tool execution via sandbox
        # For now, return a stub trace
        
        trace = ToolTrace(
            id=f"trace-{self.run.id}-{self.cycle_count}",
            idea_id=tool_call.get("idea_id"),
            tool_name=tool_call.get("type", "unknown"),
            tool_input=tool_call,
            success=True,
            stdout="[Tool execution not yet implemented]",
            stderr="",
            duration_seconds=0.1,
            tokens_used=50,
        )
        
        return trace
    
    async def _extract_micro_learnings(self, trace: ToolTrace) -> List[Memory]:
        """Extract micro-learnings from a tool trace."""
        # TODO: Call LLM to extract learnings
        # For now, return empty list
        return []
    
    def _synthesize_findings_for_idea(self, idea: ExploratoryIdea, 
                                     traces: List[ToolTrace]) -> List[Finding]:
        """Synthesize findings from tool traces for an idea."""
        # TODO: Call LLM to synthesize
        # For now, return an empty list
        return []
    
    async def _extract_idea_learnings(self, idea: ExploratoryIdea, 
                                     traces: List[ToolTrace]) -> List[Memory]:
        """Extract idea-level learnings."""
        # TODO: Call LLM to extract learnings
        # For now, return empty list
        return []
    
    def _decide_next_action_for_idea(self, idea: ExploratoryIdea) -> str:
        """Decide next action for an idea: continue, mark_explored, spawn_child, mark_blocked."""
        # TODO: Call LLM to decide
        # For now, mark as explored after first attempt
        return "mark_explored"
    
    def _apply_decision(self, idea: ExploratoryIdea, decision: str) -> None:
        """Apply LLM decision to idea status."""
        if decision == "continue_exploring":
            idea.status = IdeaStatus.IN_PROGRESS
        elif decision == "mark_explored":
            idea.status = IdeaStatus.EXPLORED
        elif decision == "spawn_child":
            idea.status = IdeaStatus.IN_PROGRESS
            # TODO: Create child idea
        elif decision == "mark_blocked":
            idea.status = IdeaStatus.BLOCKED
    
    # ========== Helpers ==========
    
    def _is_run_complete(self) -> bool:
        """Check if run should complete based on status and budget."""
        if self.run.status in ["completed", "budget_exhausted", "error", "safety_limit_reached"]:
            return True
        
        if self.run.is_budget_exhausted():
            return True
        
        # Check if all ideas are explored/blocked/deferred
        active_ideas = [i for i in self.run.ideas 
                       if i.status in [IdeaStatus.QUEUED, IdeaStatus.IN_PROGRESS]]
        if not active_ideas and self.run.ideas:
            return True
        
        return False
