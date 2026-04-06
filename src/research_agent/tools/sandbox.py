"""Sandbox isolation and path validation."""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from research_agent.core.config import settings
from research_agent.tools import PermissionError, SandboxError, TimeoutError


class PathValidator:
    """Validates file paths to prevent escaping exploration area."""

    def __init__(self, exploration_area: str):
        """Initialize with exploration area root."""
        self.exploration_root = Path(exploration_area).resolve()
        
        if not self.exploration_root.exists():
            raise ValueError(f"Exploration area does not exist: {exploration_area}")

    def validate(self, requested_path: str, mode: str = "read") -> Path:
        """
        Validate that requested path is within exploration area.
        
        Args:
            requested_path: Path the tool wants to access
            mode: "read" or "write"
            
        Returns:
            Validated absolute path
            
        Raises:
            PermissionError: If path escapes exploration area or invalid for mode
        """
        try:
            requested = Path(requested_path).resolve()
        except (OSError, ValueError) as e:
            raise PermissionError(f"Invalid path: {requested_path}") from e

        # Check if within exploration area
        try:
            requested.relative_to(self.exploration_root)
        except ValueError:
            raise PermissionError(
                f"Path {requested_path} escapes exploration area {self.exploration_root}"
            )

        # Validate based on mode
        if mode == "write":
            # Only allow writes to scratch directory
            scratch_dir = settings.sandbox.scratch_dir or str(Path(tempfile.gettempdir()) / f"research-agent")
            scratch_path = Path(scratch_dir).resolve()
            try:
                requested.relative_to(scratch_path)
            except ValueError:
                raise PermissionError(
                    f"Write access denied. Only scratch directory allowed: {scratch_dir}"
                )

        elif mode == "read":
            # Check file size
            if requested.is_file():
                size_kb = requested.stat().st_size / 1024
                if size_kb > settings.sandbox.max_file_size_kb:
                    raise PermissionError(
                        f"File too large: {size_kb:.1f}KB (max {settings.sandbox.max_file_size_kb}KB)"
                    )

        return requested

    def scan_for_secrets(self) -> Optional[list[str]]:
        """
        Scan exploration area for potential secret patterns.
        Returns list of suspicious files found.
        """
        secret_patterns = [
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "AWS_SECRET",
            "private_key",
            "password\\s*=",
        ]

        suspicious = []
        for pattern in secret_patterns:
            try:
                result = subprocess.run(
                    ["rg", pattern, str(self.exploration_root), "--max-count=1"],
                    capture_output=True,
                    timeout=5,
                    text=True,
                )
                if result.returncode == 0 and result.stdout:
                    suspicious.append(pattern)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        return suspicious if suspicious else None


class ScratchDirectory:
    """Manages temporary scratch directory for tool outputs."""

    def __init__(self, run_id: str):
        """Initialize scratch directory for a run."""
        self.run_id = run_id
        self.base_dir = Path(settings.sandbox.scratch_dir or tempfile.gettempdir()) / ".research-agent"
        self.scratch_path = self.base_dir / run_id / "scratch"
        self.scratch_path.mkdir(parents=True, exist_ok=True)

    def get_path(self, filename: str = "") -> Path:
        """Get path in scratch directory."""
        if filename:
            return self.scratch_path / filename
        return self.scratch_path

    def cleanup(self) -> None:
        """Delete scratch directory if enabled."""
        if settings.sandbox.scratch_cleanup:
            import shutil

            if self.scratch_path.exists():
                shutil.rmtree(self.scratch_path, ignore_errors=True)


class ProcessSandbox:
    """Executes commands in isolated subprocess with resource limits."""

    def __init__(self, exploration_area: str):
        """Initialize sandbox."""
        self.path_validator = PathValidator(exploration_area)
        self.exploration_area = exploration_area

    def run_command(
        self,
        cmd: list[str],
        timeout_seconds: Optional[int] = None,
        env: Optional[dict] = None,
    ) -> dict:
        """
        Run command in sandbox with timeout and environment limits.
        
        Args:
            cmd: Command to run (list)
            timeout_seconds: Timeout in seconds (uses config default if None)
            env: Environment variables to pass (uses defaults if None)
            
        Returns:
            Dict with stdout, stderr, return code, duration
        """
        timeout = timeout_seconds or settings.sandbox.tool_timeout_seconds

        # Build safe environment
        if env is None:
            env = {}
        safe_env = {
            k: v
            for k, v in __import__("os").environ.items()
            if k in settings.sandbox.allowed_env_vars
        }
        safe_env.update(env)
        safe_env["EXPLORATION_AREA"] = self.exploration_area

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                text=True,
                env=safe_env,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired as e:
            raise TimeoutError(
                f"Command execution exceeded {timeout}s timeout"
            ) from e
        except Exception as e:
            raise SandboxError(f"Command execution failed: {e}") from e
