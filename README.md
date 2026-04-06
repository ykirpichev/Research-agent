# Research-agent

LLM-driven **code exploration** agent: scoped to paths in a repo, up to 20 exploratory ideas, batched runs, path sandbox for file tools.

## Quick start

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest tests/ -q
```

Run with the **stub LLM** (no API key) or set `OPENAI_API_KEY` (optional: `RESEARCH_AGENT_MODEL`, `RESEARCH_AGENT_BASE_URL`).

```bash
python3 -m research_agent.cli start --repo . --area research_agent --state /tmp/run.json
python3 -m research_agent.cli resume --state /tmp/run.json
python3 -m research_agent.cli report --state /tmp/run.json
```

Design: [docs/auto-research-agent-design.md](docs/auto-research-agent-design.md).
