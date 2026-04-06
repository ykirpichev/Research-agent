from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

from research_agent.models import ExplorationArea, IdeaStatus, ResearchRun


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}\s*$", text)
    if m:
        text = m.group(0)
    return json.loads(text)


class LLMClient(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


class StubLLM(LLMClient):
    """Deterministic offline client for tests and dry runs."""

    def complete(self, system: str, user: str) -> str:
        if "exploratory ideas" in user.lower() or "ideas" in system.lower():
            ideas = [
                {
                    "title": "Entry points",
                    "hypothesis": "Find main modules and public APIs in the scoped area.",
                    "priority": 10,
                },
                {
                    "title": "Error handling",
                    "hypothesis": "How errors propagate and where they are caught.",
                    "priority": 5,
                },
                {
                    "title": "Configuration",
                    "hypothesis": "Where configuration is loaded and validated.",
                    "priority": 3,
                },
            ]
            return json.dumps({"ideas": ideas[:2]})
        if "tool_calls" in user.lower():
            return json.dumps(
                {
                    "tool_calls": [
                        {
                            "tool": "list_directory",
                            "args": {"path": ".", "max_entries": 50},
                            "idea_ids": [],
                        }
                    ],
                    "notes": "stub batch",
                }
            )
        if "synthesis" in user.lower() or "finding" in user.lower() or "known idea ids" in user.lower():
            ids: list[str] = []
            m = re.search(r"Known idea ids for this run:\s*([^\n]+)", user)
            if m:
                ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
            findings = []
            for iid in ids[:3] or ["placeholder"]:
                findings.append(
                    {
                        "idea_id": iid,
                        "summary": "Stub synthesis: inspected directory layout and file names in scope.",
                        "observed_vs_inferred": "mixed",
                    }
                )
            updates = [{"id": iid, "status": IdeaStatus.EXPLORED.value} for iid in ids[:3]]
            return json.dumps(
                {
                    "findings": findings,
                    "idea_status_updates": updates,
                    "global_themes": "High-level layout of the exploration area.",
                    "open_questions": "Use a real LLM (OPENAI_API_KEY) for deeper hypotheses.",
                    "done": True,
                }
            )
        return json.dumps({"error": "stub: unmatched prompt"})


class OpenAICompatibleLLM(LLMClient):
    """OpenAI-compatible chat completions (base_url + api_key)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        import httpx

        self._httpx = httpx
        self._api_key = api_key
        self._model = model
        self._base = base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        url = f"{self._base}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        with self._httpx.Client(timeout=120.0) as client:
            r = client.post(
                url,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]


def llm_from_env() -> LLMClient:
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("RESEARCH_AGENT_API_KEY")
    model = os.environ.get("RESEARCH_AGENT_MODEL", "gpt-4o-mini")
    base = os.environ.get("RESEARCH_AGENT_BASE_URL", "https://api.openai.com/v1")
    if key:
        return OpenAICompatibleLLM(api_key=key, model=model, base_url=base)
    return StubLLM()


def build_idea_generation_prompt(area: ExplorationArea, guidance: str | None, max_ideas: int) -> tuple[str, str]:
    system = (
        "You help explore a codebase. Output a single JSON object only, no markdown fences. "
        f'Format: {{"ideas": [{{"title": str, "hypothesis": str, "priority": int}}]}} '
        f"Propose at most {max_ideas} distinct exploratory ideas (short titles). "
        "Ideas should be answerable by reading/running code in the given scope."
    )
    user_parts = [
        f"Exploration roots (relative to repo): {area.root_paths!r}",
    ]
    if area.hint:
        user_parts.append(f"Natural-language scope hint: {area.hint}")
    if guidance:
        user_parts.append(f"User guidance: {guidance}")
    user = "\n".join(user_parts)
    return system, user


def parse_idea_response(raw: str, max_ideas: int) -> list[dict[str, Any]]:
    data = _extract_json_object(raw)
    ideas = data.get("ideas") if isinstance(data, dict) else None
    if not isinstance(ideas, list):
        return []
    out: list[dict[str, Any]] = []
    for item in ideas[:max_ideas]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        hyp = str(item.get("hypothesis", "")).strip()
        if not title:
            continue
        out.append(
            {
                "title": title,
                "hypothesis": hyp or title,
                "priority": int(item.get("priority") or 0),
            }
        )
    return out


def build_batch_tool_prompt(run: ResearchRun, idea_batch: list[ExploratoryIdea]) -> tuple[str, str]:
    system = (
        "You explore code via tools only. Output one JSON object, no markdown. "
        'Format: {"tool_calls": [{"tool": str, "args": object, "idea_ids": [str]}], "notes": str}. '
        "Tools: find_in_codebase (pattern regex, optional glob), "
        "read_file_range (path, start_line, optional num_lines), "
        "list_directory (path, optional max_entries), "
        "run_in_sandbox (argv list, optional timeout_sec). "
        "Stay inside the exploration area paths; use paths relative to repo root. "
        "Link each call to idea_ids when relevant."
    )
    ideas_block = json.dumps([i.to_dict() for i in idea_batch], indent=2)
    area = json.dumps(run.area.to_dict(), indent=2)
    user = (
        f"Repo root (on runner): {run.repo_root}\n"
        f"Exploration area JSON:\n{area}\n"
        f"Ideas in this batch:\n{ideas_block}\n"
        f"Tool calls used so far: {run.tool_calls_used} / {run.config.max_tool_calls_total}\n"
        "Plan useful tool_calls for this batch."
    )
    return system, user


def parse_tool_calls(raw: str) -> tuple[list[dict[str, Any]], str]:
    data = _extract_json_object(raw)
    calls = data.get("tool_calls") if isinstance(data, dict) else None
    notes = str(data.get("notes", "")) if isinstance(data, dict) else ""
    if not isinstance(calls, list):
        return [], notes
    normalized: list[dict[str, Any]] = []
    for c in calls:
        if not isinstance(c, dict):
            continue
        tool = c.get("tool")
        args = c.get("args")
        iids = c.get("idea_ids")
        if not isinstance(tool, str) or not isinstance(args, dict):
            continue
        if not isinstance(iids, list):
            iids = []
        normalized.append({"tool": tool, "args": args, "idea_ids": [str(x) for x in iids]})
    return normalized, notes


def build_synthesis_prompt(run: ResearchRun, last_tool_json: str) -> tuple[str, str]:
    system = (
        "You synthesize code exploration. Output one JSON object only. "
        'Format: {"findings": [{"idea_id": str, "summary": str, "observed_vs_inferred": str}], '
        '"idea_status_updates": [{"id": str, "status": str}], '
        '"global_themes": str, "open_questions": str, "done": bool}. '
        f"Valid statuses: {', '.join(s.value for s in IdeaStatus)}."
    )
    ideas = json.dumps([i.to_dict() for i in run.ideas], indent=2)
    known = ", ".join(i.id for i in run.ideas)
    user = (
        f"Known idea ids for this run: {known}\n\n"
        f"Ideas:\n{ideas}\n\n"
        f"Recent tool results (JSON):\n{last_tool_json}\n\n"
        "Write findings per idea_id; mark explored/blocked/skipped as appropriate. "
        "Set done true when no further tool rounds are needed."
    )
    return system, user


def parse_synthesis(raw: str) -> dict[str, Any]:
    return _extract_json_object(raw)
