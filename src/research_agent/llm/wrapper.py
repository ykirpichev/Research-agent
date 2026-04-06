"""LLM wrapper for multi-provider LLM integration using LiteLLM."""

import logging
from typing import Optional, List, Dict, Any
import json

try:
    import litellm
except ImportError:
    litellm = None

from research_agent.core.models import (
    ExploratoryIdea,
    Finding,
    Memory,
    MemoryType,
    ToolTrace,
)
from research_agent.core.config import settings

logger = logging.getLogger(__name__)


class LLMWrapper:
    """
    Wrapper around LiteLLM for unified multi-provider LLM access.
    
    Supports:
    - Multiple providers: Claude (Anthropic), GPT (OpenAI), Ollama (local), Gemini
    - Three distinct roles: Reasoner, Actor, Synthesizer
    - Cost tracking and token management
    - Structured output parsing
    """

    def __init__(self):
        """Initialize LLM wrapper with configured providers."""
        if not litellm:
            logger.warning("litellm not installed; LLM features will be unavailable")
        
        self.reasoner_model = settings.llm.planning_model
        self.actor_model = settings.llm.generation_model
        self.synthesizer_model = settings.llm.synthesis_model
        
    async def generate_ideas(
        self,
        exploration_context: str,
        prior_findings: Optional[List[Finding]] = None,
        memory_context: Optional[Dict[str, Any]] = None,
        max_to_generate: int = 5,
    ) -> List[ExploratoryIdea]:
        """
        Generate exploratory ideas using the Reasoner LLM role.
        
        Args:
            exploration_context: Description of what to explore
            prior_findings: Previous findings to build on
            memory_context: Learned patterns and knowledge
            max_to_generate: Maximum ideas to generate
            
        Returns:
            List of generated ExploratoryIdea objects
        """
        logger.info(f"Generating up to {max_to_generate} exploratory ideas")
        
        # Build context for LLM
        findings_text = ""
        if prior_findings:
            findings_text = "\n".join([f"- {f.description}" for f in prior_findings[:5]])
        
        memory_text = ""
        if memory_context:
            for key, value in memory_context.items():
                if isinstance(value, list):
                    memory_text += f"\n{key}: {', '.join(str(v) for v in value[:3])}"
                else:
                    memory_text += f"\n{key}: {value}"
        
        prompt = f"""You are a code exploration strategist. Generate {max_to_generate} novel exploratory ideas 
for understanding a codebase.

Exploration context:
{exploration_context}

{f"Prior findings: {findings_text}" if findings_text else ""}
{f"Known patterns: {memory_text}" if memory_text else ""}

Generate ideas as a JSON array. Each idea must have:
- title: Brief (5-10 word) title
- description: 1-2 sentence description
- priority: 1-5 (5=highest)

Return ONLY valid JSON array, no other text."""
        
        try:
            response = await self._call_llm(
                model=self.reasoner_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.llm.planning_temperature,
            )
            
            ideas_data = json.loads(response)
            if not isinstance(ideas_data, list):
                ideas_data = [ideas_data]
            
            ideas = []
            for data in ideas_data[:max_to_generate]:
                idea = ExploratoryIdea(
                    title=data.get("title", "Unknown"),
                    description=data.get("description", ""),
                    priority=min(5, max(1, data.get("priority", 3))),
                    exploration_area=None,  # Will be set by caller
                )
                ideas.append(idea)
            
            logger.info(f"Generated {len(ideas)} ideas")
            return ideas
            
        except Exception as e:
            logger.error(f"Error generating ideas: {e}")
            return []
    
    async def plan_exploration(
        self,
        ideas: List[ExploratoryIdea],
        prior_tool_traces: Optional[List[ToolTrace]] = None,
        remaining_budget: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Plan tool calls using the Actor LLM role.
        
        Args:
            ideas: Ideas to explore
            prior_tool_traces: Previous tool execution history
            remaining_budget: Remaining tokens, tool calls, time
            
        Returns:
            List of tool call specifications
        """
        logger.info(f"Planning exploration for {len(ideas)} ideas")
        
        ideas_text = "\n".join([f"- {i.title}: {i.description}" for i in ideas])
        
        prompt = f"""You are a code exploration planner. For each idea, determine what tools to call.

Ideas to explore:
{ideas_text}

Available tools:
- search: Search for patterns/keywords (pattern, file_type, max_results)
- read: Read file contents (file_path, optional: start_line, end_line)
- list: List directory structure (path, max_depth)

Generate a JSON array of tool calls. Each call must have:
- idea_index: 0-{len(ideas)-1} which idea this explores
- tool: "search" | "read" | "list"
- input: tool-specific input dict

Be concise. Return ONLY valid JSON array."""
        
        try:
            response = await self._call_llm(
                model=self.actor_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.llm.generation_temperature,
            )
            
            tool_calls = json.loads(response)
            if not isinstance(tool_calls, list):
                tool_calls = [tool_calls]
            
            logger.info(f"Planned {len(tool_calls)} tool calls")
            return tool_calls[:20]  # Safety limit
            
        except Exception as e:
            logger.error(f"Error planning exploration: {e}")
            return []
    
    async def synthesize_findings(
        self,
        idea: ExploratoryIdea,
        tool_traces: List[ToolTrace],
        prior_findings: Optional[List[Finding]] = None,
    ) -> List[Finding]:
        """
        Synthesize findings from tool traces using the Synthesizer role.
        
        Args:
            idea: Idea that was explored
            tool_traces: Tool execution results
            prior_findings: Previous findings for this idea
            
        Returns:
            List of synthesized Finding objects
        """
        logger.info(f"Synthesizing findings for idea: {idea.title}")
        
        if not tool_traces:
            return []
        
        traces_text = "\n".join([
            f"Tool: {t.tool_name}, Success: {t.success}, Output: {t.stdout[:200]}"
            for t in tool_traces[:5]
        ])
        
        prompt = f"""Synthesize findings from tool execution.

Idea: {idea.title}
Description: {idea.description}

Tool results:
{traces_text}

Extract key findings as a JSON array. Each finding should have:
- description: What was discovered (1-2 sentences)
- locations: List of code locations if applicable [optional]
- confidence: 0-1 confidence score

Return ONLY valid JSON array."""
        
        try:
            response = await self._call_llm(
                model=self.synthesizer_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.llm.synthesis_temperature,
            )
            
            findings_data = json.loads(response)
            if not isinstance(findings_data, list):
                findings_data = [findings_data]
            
            findings = []
            for data in findings_data:
                finding = Finding(
                    idea_id=idea.id,
                    description=data.get("description", ""),
                    code_locations=data.get("locations", []),
                    confidence=float(data.get("confidence", 0.5)),
                )
                findings.append(finding)
            
            logger.info(f"Synthesized {len(findings)} findings")
            return findings
            
        except Exception as e:
            logger.error(f"Error synthesizing findings: {e}")
            return []
    
    async def extract_learnings(
        self,
        tool_trace: ToolTrace,
        idea: ExploratoryIdea,
        existing_patterns: Optional[List[Memory]] = None,
    ) -> List[Memory]:
        """
        Extract learnings from tool execution (micro-learning).
        
        Args:
            tool_trace: Tool execution trace
            idea: Idea being explored
            existing_patterns: Known patterns to avoid duplicates
            
        Returns:
            List of extracted Memory objects
        """
        if not tool_trace.success:
            return []
        
        prompt = f"""Extract key learnings from tool output.

Idea: {idea.title}
Tool: {tool_trace.tool_name}
Output excerpt: {tool_trace.stdout[:300]}

Identify 1-2 high-confidence patterns or facts as JSON:
{{
  "learnings": [
    {{"type": "pattern|observation|structure", "text": "..."}}
  ]
}}

Return ONLY valid JSON."""
        
        try:
            response = await self._call_llm(
                model=self.synthesizer_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.llm.synthesis_temperature,
            )
            
            data = json.loads(response)
            memories = []
            
            for learning in data.get("learnings", [])[:2]:
                memory_type = learning.get("type", "pattern").upper()
                if memory_type not in ["PATTERN", "OBSERVATION", "STRUCTURE"]:
                    memory_type = "PATTERN"
                
                memory = Memory(
                    memory_type=MemoryType[memory_type],
                    description=learning.get("text", ""),
                    source_idea_id=idea.id if idea else None,
                    persist=False,
                )
                memories.append(memory)
            
            return memories
            
        except Exception as e:
            logger.error(f"Error extracting learnings: {e}")
            return []
    
    async def decide_next_action(
        self,
        idea: ExploratoryIdea,
        findings: Optional[List[Finding]] = None,
    ) -> str:
        """
        Decide next action for an idea: continue, mark_explored, spawn_child, or mark_blocked.
        
        Args:
            idea: Idea to decide on
            findings: Findings collected so far
            
        Returns:
            Action string: "continue_exploring", "mark_explored", "spawn_child", or "mark_blocked"
        """
        findings_count = len(findings) if findings else 0
        
        prompt = f"""Decide next action for exploration.

Idea: {idea.title}
Findings so far: {findings_count}
Status: {idea.status}

Possible actions:
- continue_exploring: Keep exploring, more to discover
- mark_explored: Sufficiently explored, move on
- spawn_child: Spawn follow-up idea
- mark_blocked: Blocked, cannot proceed

Return ONLY one of: continue_exploring | mark_explored | spawn_child | mark_blocked"""
        
        try:
            response = await self._call_llm(
                model=self.reasoner_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.llm.planning_temperature,
            )
            
            action = response.strip().lower()
            valid_actions = ["continue_exploring", "mark_explored", "spawn_child", "mark_blocked"]
            
            if action not in valid_actions:
                return "mark_explored"  # Default
            
            return action
            
        except Exception as e:
            logger.error(f"Error deciding next action: {e}")
            return "mark_explored"
    
    # ========== Internal Methods ==========
    
    async def _call_llm(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Call LLM via LiteLLM with error handling.
        
        Args:
            model: Model name (e.g. "gpt-4", "claude-3-sonnet", "ollama/llama2")
            messages: Conversation messages
            temperature: Sampling temperature
            max_tokens: Max tokens in response
            
        Returns:
            Response text
        """
        if not litellm:
            logger.warning("litellm not available; returning stub response")
            return "{}"
        
        if max_tokens is None:
            max_tokens = settings.llm.max_tokens_per_call
        
        try:
            # Use litellm.completion for async-compatible call
            response = litellm.completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            # Extract message content
            if hasattr(response, "choices"):
                return response.choices[0].message.content
            
            return str(response)
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
