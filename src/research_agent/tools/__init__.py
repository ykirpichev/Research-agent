"""Sandbox tools for code exploration."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    data: Any = None

    def excerpt_stdout(self, max_chars: int = 500) -> str:
        """Get excerpt of stdout."""
        return self.stdout[:max_chars] + ("..." if len(self.stdout) > max_chars else "")

    def excerpt_stderr(self, max_chars: int = 500) -> str:
        """Get excerpt of stderr."""
        return self.stderr[:max_chars] + ("..." if len(self.stderr) > max_chars else "")


class SandboxError(Exception):
    """Base exception for sandbox errors."""

    pass


class PermissionError(SandboxError):
    """Raised when access is denied."""

    pass


class TimeoutError(SandboxError):
    """Raised when tool execution times out."""

    pass


class SandboxTool(ABC):
    """Abstract base class for sandbox tools."""

    def __init__(self, exploration_area: str):
        """Initialize tool with exploration area."""
        self.exploration_area = exploration_area

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with given arguments."""
        pass

    @abstractmethod
    def validate_args(self, **kwargs: Any) -> bool:
        """Validate tool arguments."""
        pass
