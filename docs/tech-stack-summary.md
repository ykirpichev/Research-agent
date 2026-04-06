# Tech Stack Summary

## Backend

| Component | Choice | Why |
|-----------|--------|-----|
| **Language** | Python 3.10+ | Fast iteration, rich LLM SDKs, type hints |
| **LLM Interface** | LiteLLM | Multi-provider support (Claude, OpenAI, local Ollama, Gemini, etc.) |
| **ORM** | SQLAlchemy 2.0 | Type-safe, flexible, production-ready |
| **Database** | SQLite + JSON | Hybrid: SQLite for queries, JSON for reports & debugging |
| **CLI** | Typer | Modern, auto-docs, async-friendly |
| **REST API** | FastAPI | Async, auto OpenAPI, production-ready |
| **ASGI Server** | Uvicorn | High performance, standards-compliant |
| **Config** | Pydantic Settings | Type-safe, .env support, validation |
| **Dependency Mgmt** | Poetry | Lock files, reproducible builds |
| **Search Tool** | ripgrep (subprocess) | Fast, memory-efficient, external process |

## Sandbox Strategy

| Layer | Phase 1 (v0.1-0.2) | Phase 2 (v0.3+) |
|-------|-------------------|-----------------|
| **Mechanism** | Path validation + subprocess | Podman/systemd-nspawn |
| **Overhead** | Minimal | ~50-200ms per tool |
| **Safety** | Good (if validation thorough) | Excellent (OS-enforced) |
| **Setup** | None | Install Podman or systemd |
| **Cross-platform** | macOS/Linux/Windows | macOS/Linux |
| **Network** | No | No (--network=none) |
| **File System** | Read-only codebase + scratch temp | Read-only bind mount + tmpfs |
| **Resource Limits** | OS process limits | cgroups: 512MB, 1 CPU, 10s timeout |

## Directory Structure (v0.1)

```
research-agent/
├── README.md
├── pyproject.toml                    # Poetry config
├── poetry.lock                       # Locked dependencies
├── Makefile                          # Common tasks
│
├── src/
│   └── research_agent/
│       ├── __init__.py
│       ├── main.py                   # CLI entry point
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py                # FastAPI app
│       │   └── routes/
│       │       ├── runs.py
│       │       └── memory.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── orchestrator.py       # Main loop
│       │   ├── models.py             # Pydantic models
│       │   └── config.py             # Settings
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── generator.py          # Idea generator LLM calls
│       │   ├── planner.py            # Exploration planner
│       │   └── synthesizer.py        # Synthesizer
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py               # Tool interface
│       │   ├── search.py             # ripgrep wrapper
│       │   ├── reader.py             # File reader
│       │   ├── lister.py             # Directory lister
│       │   └── sandbox.py            # Sandbox isolation
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── index.py              # Memory index
│       │   ├── storage.py            # SQLAlchemy models
│       │   └── learner.py            # Extract learnings
│       ├── llm/
│       │   ├── __init__.py
│       │   └── wrapper.py            # LiteLLM wrapper
│       └── storage/
│           ├── __init__.py
│           ├── db.py                 # SQLAlchemy session
│           └── models.py             # DB models
│
├── tests/
│   ├── __init__.py
│   ├── test_orchestrator.py
│   ├── test_tools.py
│   ├── test_sandbox.py
│   ├── test_memory.py
│   └── conftest.py                   # Pytest fixtures
│
├── docs/
│   ├── auto-research-agent-design.md
│   ├── framework-and-sandbox-strategy.md
│   ├── API.md                        # REST API docs
│   ├── CLI.md                        # CLI usage
│   └── examples/
│       ├── basic_exploration.md
│       └── local_llm_setup.md
│
└── .research-agent/                  # Runtime data (gitignored)
    ├── research.db
    ├── config.yaml
    ├── memory-index.json
    └── runs/
```

## Key Configuration (config.yaml)

```yaml
# LLM Configuration
llm:
  default_provider: "claude"  # or "openai", "local/ollama", "gemini"
  
  # Role-specific models
  models:
    generation: "claude-3-5-sonnet-20241022"
    planning: "claude-3-5-sonnet-20241022"
    synthesis: "claude-3-5-sonnet-20241022"
  
  # Provider configs
  providers:
    claude:
      api_key: "${ANTHROPIC_API_KEY}"
    openai:
      api_key: "${OPENAI_API_KEY}"
    local:
      base_url: "http://localhost:11434"
      model: "llama2"

# Sandbox Configuration
sandbox:
  mode: "path-validation"  # "podman" for Phase 2
  max_file_size: "50KB"
  max_search_results: 100
  tool_timeout_seconds: 10
  network_enabled: false
  environment_vars:
    - PATH
    - HOME

# Research Run Configuration
research:
  max_exploratory_ideas: 20
  batch_size: 5
  batch_max_tokens: 8000
  max_tool_calls_per_idea: 10
  wall_clock_limit_seconds: 3600  # 1 hour
  exploration_depth: "medium"

# Storage Configuration
storage:
  database: "sqlite:///.research-agent/research.db"
  memory_index: ".research-agent/memory-index.json"
  reports_dir: ".research-agent/runs/reports"
```

## Development Setup

```bash
# 1. Clone and create virtual env
git clone https://github.com/ykirpichev/Research-agent.git
cd Research-agent
poetry install

# 2. Set up LLM provider
export ANTHROPIC_API_KEY="sk-ant-..."
# OR for local: start Ollama
# ollama run llama2

# 3. Run CLI
poetry run research-agent explore src/auth --max-ideas 10 --report-format markdown

# 4. Start REST API (separate terminal)
poetry run uvicorn research_agent.api.app:app --reload

# 5. Run tests
poetry run pytest -v
```

## MVP Scope (Phase 0.1)

### Must-Have:
- ✅ Orchestrator loop
- ✅ Path validation sandbox
- ✅ Single unified LLM role (combine 3)
- ✅ SQLite storage
- ✅ Simple memory index (JSON)
- ✅ CLI interface
- ✅ Read-only tools: search, read, list
- ✅ Report generation (markdown)

### Nice-to-Have (Phase 0.2+):
- 3 separate LLM roles
- Memory learning stage
- REST API
- JSON report export
- Container support

### No Initial Support:
- ❌ Tool execution (run tests, compile)
- ❌ Symbol resolution (needs LSP)
- ❌ Network access
- ❌ UI/Dashboard
- ❌ Multi-repo learning
