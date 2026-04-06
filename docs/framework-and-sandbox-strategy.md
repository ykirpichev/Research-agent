# Framework & Sandbox Strategy

## 1. Technology Stack

### Core Language: Python

**Why Python:**
- Rapid iteration for agent logic
- Rich LLM SDKs (LangChain, LiteLLM, llamaindex)
- Mature tooling: Poetry for dependency management
- Good for prototyping; can optimize hot paths if needed

**Python Version:** 3.10+ (type hints, pattern matching)

### LLM Integration: Multi-Provider Support (LiteLLM)

**Strategy: Provider Abstraction Layer**

Use **LiteLLM** as the unified LLM interface. This allows:
- Switch between providers without rewriting code
- Supported providers:
  - **Local**: Ollama, vLLM, LM Studio (free, private)
  - **API**: Claude (Anthropic), ChatGPT (OpenAI), Gemini (Google), others
  - **Custom**: Any OpenAI-compatible endpoint

**Configuration:**
```yaml
# config.yaml
llm:
  default_provider: "claude"  # or "local/ollama", "openai", "gemini"
  models:
    generation: "claude-3-5-sonnet-20241022"
    planning: "claude-3-5-sonnet-20241022"
    synthesis: "claude-3-5-sonnet-20241022"
  api_keys:
    anthropic: "${ANTHROPIC_API_KEY}"
    openai: "${OPENAI_API_KEY}"
    local_base_url: "http://localhost:11434"  # Ollama
```

**Benefits:**
- Easy local testing with Ollama
- Production flexibility
- Cost optimization (use cheaper model for planning, better model for synthesis)

### Storage: Hybrid (SQLite + JSON)

**SQLite for:**
- Run state (ResearchRun, ExploratoryIdea, ToolTrace)
- Memory index (queryable)
- Batch cursor, budget tracking
- Schema migration support

**JSON for:**
- Final exploration reports (human-readable export)
- Findings summaries (easy to import into other tools)
- Memory snapshots (readable, debuggable)

**Directory structure:**
```
.research-agent/
  ├── research.db              # SQLite database
  ├── memory-index.json        # Memory index (queryable snapshots)
  ├── runs/
  │   ├── run_001.json         # Full run state (for debugging)
  │   ├── run_002.json
  │   └── reports/
  │       ├── run_001_report.md
  │       └── run_002_report.json
  └── config.yaml              # Agent config (provider, budgets, etc.)
```

**ORM/Query Library:** SQLAlchemy (declarative, flexible)

### User Interface: CLI + REST API

**CLI Framework: Typer**
- Simple, modern, auto-docs
- Example:
  ```bash
  $ research-agent explore src/auth \
    --seed-ideas "How does auth flow?" "What are auth patterns?" \
    --max-ideas 15 \
    --llm-provider claude \
    --report-format markdown
  ```

**REST API Framework: FastAPI**
- Async-first
- Auto OpenAPI docs
- Runs in parallel with CLI
- Example endpoints:
  ```
  POST   /api/v1/runs              # Start new exploration
  GET    /api/v1/runs/{id}         # Get run status
  GET    /api/v1/runs/{id}/findings
  POST   /api/v1/runs/{id}/abort   # Stop exploration
  GET    /api/v1/memory/query      # Query memories
  ```

### Build & Dependency Management: Poetry

```toml
# pyproject.toml
[tool.poetry]
name = "research-agent"
version = "0.1.0"
description = "LLM-driven autonomous code exploration"

[tool.poetry.dependencies]
python = "^3.10"
litellm = "^1.0"          # Multi-provider LLM
sqlalchemy = "^2.0"       # ORM
typer = "^0.9"            # CLI
fastapi = "^0.109"        # REST API
uvicorn = "^0.27"         # ASGI server
pydantic = "^2.0"         # Data validation
pydantic-settings = "^2.0"
ripgrep = "^0.0.14"       # For searching (or shell subprocess)
python-dotenv = "^1.0"    # Config from .env

[tool.poetry.dev-dependencies]
pytest = "^7.4"
pytest-asyncio = "^0.21"
pytest-cov = "^4.1"
black = "^23.0"
ruff = "^0.1"
mypy = "^1.0"
```

---

## 2. Sandbox Architecture: Phased Approach

### Phase 1 (v0.1-0.2): Read-Only Local Execution

**Goal:** Get core agent working safely with minimal infrastructure.

**Implementation:**
```
┌─────────────────────────────────────────────────────────┐
│ Research Agent (Python process)                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Tool Executor:                                         │
│  ├─ Validate path is within exploration_area           │
│  ├─ Sandboxed subprocess (Python's subprocess module)  │
│  ├─ Inherit ONLY necessary env vars (no secrets)       │
│  └─ No write access to codebase                        │
│                                                         │
└─────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ Sandboxed Tool Execution (subprocess)                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. ripgrep search (read file system only)             │
│  2. read file (bounded by max_size, path validation)   │
│  3. list directory (traversal limited to exploration)  │
│  4. No execution of arbitrary code                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
         ↓
    Source Code
    (read-only mount or validated path)
```

**Safety Mechanisms (v0.1):**

| Layer | Mechanism | How |
|-------|-----------|-----|
| **Path Validation** | Whitelist exploration area | Reject paths outside `exploration_area` root; convert to absolute; check for `../` traversal |
| **Tool Allowlist** | Only safe tools | search, read, list (no run, shell exec) |
| **Memory Limits** | Bounded reads | Max 50KB per read; max 1000 lines per file; timeout 10s per search |
| **Environment** | Minimal env | Pass only: `PATH`, `HOME` (temp dir), `CODEBASE_ROOT` |
| **Subprocess Isolation** | Limited permissions | Run as same user; no CAP_SYS_ADMIN; no network access |

**File Path Validation Code:**
```python
from pathlib import Path

def validate_path(requested_path: str, exploration_area: str) -> Path:
    """
    Ensure requested_path is within exploration_area.
    Raises PermissionError if path escapes.
    """
    requested = Path(requested_path).resolve()
    area_root = Path(exploration_area).resolve()
    
    # Check if path is within exploration area
    try:
        requested.relative_to(area_root)
    except ValueError:
        raise PermissionError(f"Path {requested_path} escapes exploration area {exploration_area}")
    
    return requested
```

**Example Tool Implementation:**
```python
class SandboxedSearch:
    def __init__(self, exploration_area: str):
        self.area = Path(exploration_area).resolve()
    
    def search(self, pattern: str, timeout: int = 10) -> list[str]:
        """
        Search within exploration_area using ripgrep.
        Output is read-only; no side effects.
        """
        cmd = [
            "rg", 
            "--type-list",  # Show supported types
            pattern,
            str(self.area),
            "--max-count=100",   # Limit results
            "--timeout=10s"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                text=True
            )
            return result.stdout.split('\n')
        except subprocess.TimeoutExpired:
            return ["[TIMEOUT] Search exceeded {timeout}s limit"]
```

**Scratch Directory (for temporary tool outputs):**
- Temporary: `/tmp/research-agent/{run_id}/scratch/`
- Deleted after run completion
- Used ONLY for tool output staging (test results, logs)
- NO persistent writes by tools

### Phase 2 (v0.3-0.5): Lightweight Container (Podman/systemd-nspawn)

**Upgrade to lightweight isolation when needed.**

**Why Phase 2, not Phase 1?**
- Phase 1 proves core agent logic first
- Container adds deployment complexity
- Read-only + path validation sufficient for most use cases

**Podman (If Needed):**
- Rootless containers (no privileges needed)
- Drop-in Docker replacement, lighter weight
- Snapshot of codebase mounted read-only
- Tools run inside container with strict limits

```bash
# Sandbox container definition
podman run --rm \
  --read-only \
  --memory=512m \
  --cpus=1 \
  --timeout=5s \
  --mount type=bind,src=/path/to/codebase,dst=/code,readonly \
  --mount type=tmpfs,dst=/scratch,size=100m \
  --network=none \
  research-agent-sandbox:latest \
  rg "pattern" /code
```

**systemd-nspawn (If Linux-Only is OK):**
- Even lighter: minimal kernel namespaces
- No daemon overhead
- Perfect for CI/local development

```bash
systemd-nspawn \
  --read-only \
  --bind-ro=/path/to/codebase:/code \
  --bind=/tmp/scratch:/scratch \
  search-tool-binary "pattern"
```

### Phase 3 (v0.6+): Full Hardened Container (Docker)

**Only if:**
- Agent runs on untrusted machines (CI/cloud)
- Multiple concurrent runs need isolation
- Need to sandbox LLM itself (not just tools)

---

## 3. Sandbox Isolation Details

### 3.1 File System Isolation

**Phase 1 (Read-Only + Validation):**
```
Exploration Area: /home/user/myproject/src
├── auth/              ✓ Agent can read
├── payment/           ✓ Agent can read
├── admin/             ✓ Agent can read (if in scope)
├── .git/              ✓ Agent can read (useful for history)
└── ../secrets.yaml    ✗ BLOCKED (outside exploration_area)

Scratch (Writable):
/tmp/research-agent/{run_id}/scratch/
├── test_output.json   ✓ Temporary tool results
├── search_results.txt ✓ Search staging
└── [auto-deleted after run]
```

**Runtime Validation:**
```python
# Before any file access
def authorize_file_access(path: str, exploration_area: str, mode: str):
    validated_path = validate_path(path, exploration_area)
    
    if mode == "write":
        # Only allow writes to scratch directory
        if not str(validated_path).startswith("/tmp/research-agent"):
            raise PermissionError("Write access denied outside scratch")
    
    return validated_path
```

### 3.2 Process Isolation

**Phase 1 (Subprocess):**
- No special isolation; same user/group
- Limited by OS resource controls
- Timeout enforcement in Python (no infinite loops)

**Environment Variables Passed:**
```python
env = {
    "PATH": os.environ.get("PATH", ""),
    "HOME": f"/tmp/research-agent/{run_id}",  # Temp home
    "CODEBASE_ROOT": str(exploration_area),
    "EXPLORATION_DEPTH": "3",  # Custom: don't traverse too deep
    # NOT passed: AWS_SECRET_ACCESS_KEY, SSH_KEYS, etc.
}
subprocess.run(cmd, env=env, ...)
```

**Timeout Enforcement:**
```python
def run_tool_with_timeout(cmd, timeout: int = 10):
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            text=True
        )
        return result
    except subprocess.TimeoutExpired:
        # Kill the process, log, return error
        return {"error": "timeout", "duration": timeout}
```

### 3.3 Network Isolation

**Phase 1 & 2: No Network**
- Tools run with `--network=none` (container) or implicit no-network (subprocess)
- If tool needs external resource: **mark as blocked, defer**

**Example:** Tool that needs to call API:
```python
# Tool execution attempt
search_npm_registry("lodash")
# Result: Error - network not available - mark idea as deferred
```

### 3.4 Secret Prevention

**Scanning mechanism:**
- Before run starts: scan exploration_area for common secret patterns
- Warn user if `.env`, AWS keys, credentials found
- Do NOT pass to tools/LLM

```python
SECRET_PATTERNS = [
    r"ANTHROPIC_API_KEY",
    r"OPENAI_API_KEY",
    r"AWS_SECRET",
    r"private_key",
    r"password\s*=",
]

def scan_for_secrets(directory: str):
    """Warn if secrets might be in the directory."""
    for pattern in SECRET_PATTERNS:
        results = subprocess.run(
            ["rg", pattern, directory],
            capture_output=True
        )
        if results.stdout:
            print(f"⚠️  WARNING: Found potential secret patterns in {directory}")
```

---

## 4. Sandbox Configuration & Defaults

Add to `config.yaml`:

```yaml
sandbox:
  # Phase 1: Read-only validation
  mode: "path-validation"  # Or "podman" (future)
  
  # File access limits
  max_file_size: "50KB"
  max_line_count: 1000
  max_search_results: 100
  
  # Process limits
  tool_timeout_seconds: 10
  max_concurrent_tools: 3
  
  # Network
  network_enabled: false  # Always off in v0.1
  
  # Environment
  environment_vars:
    - PATH
    - HOME  # Set to temp dir
  
  # Scratch space
  scratch_dir_size: "100MB"
  scratch_cleanup: true  # Delete after run
```

---

## 5. Implementation Roadmap

### v0.1 (MVP)
- [ ] Core orchestrator loop
- [ ] Path validation + subprocess tools
- [ ] SQLite storage for runs
- [ ] Single LLM role (combine all 3)
- [ ] CLI interface (basic)
- [ ] Local JSON memory index
- [ ] No execution; read-only tools only

### v0.2
- [ ] Split into 3 LLM roles (generate, plan, synthesize)
- [ ] Memory learning & persistence
- [ ] REST API stub
- [ ] Report generation (markdown + JSON)

### v0.3
- [ ] Podman container option
- [ ] Selective tool execution (if safe)
- [ ] Concurrency for batches
- [ ] Memory cross-run queries

### v0.4+
- [ ] Symbol resolution
- [ ] Docker option
- [ ] Cloud deployment
- [ ] UI dashboard

---

## 6. Security Checklist

Before claiming sandbox is "safe":

- [ ] Path validation prevents `../` escape
- [ ] No write access to codebase (scratch only)
- [ ] No network access by default
- [ ] Secret patterns scanned before run
- [ ] Environment vars explicitly allowlisted
- [ ] Tool execution times out
- [ ] Tool results sanitized before LLM ingestion
- [ ] Memory stores no code, only references
- [ ] Run state encrypted if persisted to shared storage
- [ ] Concurrent runs use isolated scratch dirs

---

## 7. Trade-Offs: Phase 1 vs Containers

| Aspect | Phase 1 (Path Validation) | Podman (Future) |
|--------|---------------------------|-----------------|
| Complexity | Low (Python subprocess) | Medium (container management) |
| Safety | Good (if path validation is thorough) | Excellent (OS-enforced) |
| Performance | Fast (no container overhead) | Slower (50-200ms per tool) |
| Dev Experience | Immediate (no setup) | Setup needed (install Podman) |
| Debugging | Easy (same OS) | Harder (inside container) |
| Cross-platform | macOS/Linux/Windows | macOS/Linux (Podman on Windows needs WSL) |

**Recommendation:** Start with Phase 1. Validate path safety. Move to Phase 2 if:
- Agent runs on untrusted machines
- Multiple concurrent runs needed
- External deployments required
