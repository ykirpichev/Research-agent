from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_agent.models import RunConfig
from research_agent.sandbox import PathSandbox


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any]
    stdout: str
    stderr: str


class CodeTools:
    def __init__(self, sandbox: PathSandbox, config: RunConfig) -> None:
        self._sb = sandbox
        self._config = config

    def find_in_codebase(self, pattern: str, glob: str | None = None) -> ToolResult:
        if not pattern or len(pattern) > 500:
            return ToolResult(False, {"error": "invalid pattern"}, "", "pattern empty or too long")
        files = self._sb.iter_area_files()
        if glob:
            import fnmatch

            files = [p for p in files if fnmatch.fnmatch(p.name, glob) or fnmatch.fnmatch(str(p.relative_to(self._sb.repo_root)), glob)]
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(False, {"error": f"invalid regex: {e}"}, "", str(e))
        matches: list[dict[str, Any]] = []
        for path in files:
            if path.suffix in {".png", ".jpg", ".gif", ".ico", ".woff", ".zip"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(self._sb.repo_root)).replace("\\", "/")
            for i, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append({"path": rel, "line": i, "text": line[:500]})
                    if len(matches) >= self._config.search_max_matches:
                        break
            if len(matches) >= self._config.search_max_matches:
                break
        return ToolResult(True, {"matches": matches, "truncated": len(matches) >= self._config.search_max_matches}, "", "")

    def read_file_range(self, path: str, start_line: int = 1, num_lines: int | None = None) -> ToolResult:
        if start_line < 1:
            return ToolResult(False, {"error": "start_line must be >= 1"}, "", "bad start_line")
        n = num_lines if num_lines is not None else self._config.read_file_max_lines
        if n < 1 or n > self._config.read_file_max_lines:
            n = min(max(n, 1), self._config.read_file_max_lines)
        full = self._sb.resolve_under_area(path)
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return ToolResult(False, {"error": str(e)}, "", str(e))
        lines = text.splitlines()
        end = min(len(lines), start_line - 1 + n)
        chunk = lines[start_line - 1 : end]
        numbered = [f"{start_line + i}|{chunk[i]}" for i in range(len(chunk))]
        return ToolResult(
            True,
            {
                "path": path.replace("\\", "/"),
                "start_line": start_line,
                "lines_returned": len(chunk),
                "total_lines": len(lines),
                "content": "\n".join(numbered),
            },
            "",
            "",
        )

    def list_directory(self, path: str, max_entries: int = 100) -> ToolResult:
        full = self._sb.resolve_under_area(path)
        if not full.is_dir():
            return ToolResult(False, {"error": "not a directory"}, "", "not a directory")
        entries: list[dict[str, str]] = []
        for child in sorted(full.iterdir()):
            if self._sb.is_excluded(child):
                continue
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                }
            )
            if len(entries) >= max_entries:
                break
        rel = str(full.relative_to(self._sb.repo_root)).replace("\\", "/")
        return ToolResult(
            True,
            {"path": rel, "entries": entries, "truncated": len(entries) >= max_entries},
            "",
            "",
        )

    def run_in_sandbox(self, argv: list[str], timeout_sec: float = 30.0) -> ToolResult:
        """
        Run a command with cwd=repo_root. Phase-1 safety: argv must be a non-empty
        list of strings (no shell). Network is not disabled here — use container
        integration in a later phase for full isolation.
        """
        if not argv or not all(isinstance(a, str) for a in argv):
            return ToolResult(False, {"error": "argv must be non-empty list of strings"}, "", "bad argv")
        if timeout_sec <= 0 or timeout_sec > 300:
            timeout_sec = min(max(timeout_sec, 1.0), 300.0)
        try:
            proc = subprocess.run(
                argv,
                cwd=self._sb.repo_root,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env={**os.environ, "CI": "1"},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, {"error": "timeout"}, "", "command timed out")
        except Exception as e:
            return ToolResult(False, {"error": str(e)}, "", str(e))
        out = (proc.stdout or "")[-8000:]
        err = (proc.stderr or "")[-8000:]
        return ToolResult(
            proc.returncode == 0,
            {"returncode": proc.returncode},
            out,
            err,
        )

    def dispatch(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        t0 = time.perf_counter()
        try:
            if tool_name == "find_in_codebase":
                return self.find_in_codebase(str(args.get("pattern", "")), args.get("glob"))
            if tool_name == "read_file_range":
                return self.read_file_range(
                    str(args.get("path", "")),
                    int(args.get("start_line") or 1),
                    args.get("num_lines"),
                )
            if tool_name == "list_directory":
                return self.list_directory(str(args.get("path", ".")), int(args.get("max_entries") or 100))
            if tool_name == "run_in_sandbox":
                argv = args.get("argv")
                if not isinstance(argv, list):
                    return ToolResult(False, {"error": "argv must be a list"}, "", "bad argv")
                to = float(args.get("timeout_sec") or 30.0)
                return self.run_in_sandbox([str(x) for x in argv], to)
            return ToolResult(False, {"error": f"unknown tool: {tool_name}"}, "", "unknown tool")
        finally:
            _ = time.perf_counter() - t0  # reserved for future metrics
