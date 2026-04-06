from __future__ import annotations

import fnmatch
import os
from pathlib import Path


class PathSandbox:
    """Resolve and validate paths so tools only touch the repo + exploration area."""

    def __init__(self, repo_root: Path, area_roots: list[str], exclude_globs: list[str]) -> None:
        self.repo_root = repo_root.resolve()
        roots = area_roots if area_roots else ["."]
        self._area_roots = [self._normalize_root(r) for r in roots]
        self._exclude = list(exclude_globs)

    def _normalize_root(self, rel: str) -> Path:
        p = (self.repo_root / rel).resolve()
        if self.repo_root not in p.parents and p != self.repo_root:
            raise ValueError(f"Area root escapes repo: {rel}")
        if not str(p).startswith(str(self.repo_root)):
            raise ValueError(f"Area root escapes repo: {rel}")
        return p

    def is_excluded(self, path: Path) -> bool:
        try:
            rel = path.resolve().relative_to(self.repo_root)
        except ValueError:
            return True
        s = str(rel).replace(os.sep, "/")
        for pat in self._exclude:
            if fnmatch.fnmatch(s, pat) or fnmatch.fnmatch(os.path.basename(s), pat):
                return True
        return False

    def resolve_under_area(self, rel_path: str) -> Path:
        """Resolve a path relative to repo root; must fall under one area root."""
        cleaned = rel_path.replace("\\", "/").lstrip("/")
        if cleaned in (".", ""):
            if not self._area_roots:
                raise ValueError("no exploration roots")
            return self._area_roots[0]
        if ".." in Path(cleaned).parts:
            raise ValueError("Path traversal not allowed")
        full = (self.repo_root / cleaned).resolve()
        if self.repo_root not in full.parents and full != self.repo_root:
            raise ValueError("Path outside repository")
        if not full.exists():
            raise FileNotFoundError(cleaned)
        under = False
        for root in self._area_roots:
            if full == root or root in full.parents:
                under = True
                break
        if not under:
            raise ValueError(f"Path not in exploration area: {cleaned}")
        if self.is_excluded(full):
            raise ValueError(f"Path excluded by glob: {cleaned}")
        return full

    def iter_area_files(self) -> list[Path]:
        out: list[Path] = []
        for root in self._area_roots:
            if not root.exists():
                continue
            if root.is_file():
                if not self.is_excluded(root):
                    out.append(root)
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dp = Path(dirpath)
                dirnames[:] = [
                    d
                    for d in dirnames
                    if not self.is_excluded(dp / d)
                    and d not in (".git", "__pycache__", ".venv", "node_modules")
                ]
                for name in filenames:
                    p = dp / name
                    if self.is_excluded(p):
                        continue
                    out.append(p)
        return sorted(set(out))
