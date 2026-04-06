"""Read tool: Read file contents."""

import time
from pathlib import Path
from typing import Any, Optional

from research_agent.core.config import settings
from research_agent.tools import PermissionError, ToolResult, SandboxTool
from research_agent.tools.sandbox import PathValidator


class ReadTool(SandboxTool):
    """Read file contents with bounds checking."""

    def __init__(self, exploration_area: str):
        """Initialize read tool."""
        super().__init__(exploration_area)
        self.path_validator = PathValidator(exploration_area)

    def validate_args(self, **kwargs: Any) -> bool:
        """Validate read arguments."""
        if "file_path" not in kwargs:
            return False
        file_path = kwargs["file_path"]
        return isinstance(file_path, str) and len(file_path) > 0

    async def execute(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Read file contents.
        
        Args:
            file_path: Path to file
            start_line: Optional start line (1-indexed)
            end_line: Optional end line (1-indexed, inclusive)
            
        Returns:
            ToolResult with file contents
        """
        if not self.validate_args(file_path=file_path):
            return ToolResult(
                success=False, error_message="Invalid read arguments"
            )

        try:
            # Validate path
            validated_path = self.path_validator.validate(file_path, mode="read")

            # Check file exists
            if not validated_path.is_file():
                return ToolResult(
                    success=False, error_message=f"File not found: {validated_path}"
                )

            start_time = time.time()

            # Read file
            with open(validated_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            # Apply line filters
            if start_line is not None or end_line is not None:
                start = max(0, (start_line or 1) - 1)
                end = min(len(lines), (end_line or len(lines)))
                lines = lines[start:end]

            # Check line count
            if len(lines) > settings.sandbox.max_line_count:
                return ToolResult(
                    success=False,
                    error_message=f"File too many lines: {len(lines)} (max {settings.sandbox.max_line_count})",
                )

            content = "".join(lines)
            duration = time.time() - start_time

            return ToolResult(
                success=True,
                stdout=content,
                duration_seconds=duration,
                data={
                    "path": str(validated_path),
                    "lines": len(lines),
                    "start_line": start_line or 1,
                    "end_line": end_line or len(lines),
                },
            )

        except PermissionError as e:
            return ToolResult(success=False, error_message=str(e))
        except Exception as e:
            return ToolResult(
                success=False, error_message=f"Read tool error: {e}"
            )


# Convenience function
async def read_file(
    exploration_area: str,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    **kwargs: Any,
) -> ToolResult:
    """Convenience function to read file."""
    tool = ReadTool(exploration_area)
    return await tool.execute(
        file_path=file_path, start_line=start_line, end_line=end_line, **kwargs
    )
