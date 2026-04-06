"""List tool: List directory contents and structure."""

import os
import time
from pathlib import Path
from typing import Any, Optional

from research_agent.core.config import settings
from research_agent.tools import ToolResult, SandboxTool
from research_agent.tools.sandbox import PathValidator


class ListTool(SandboxTool):
    """List directory contents."""

    def __init__(self, exploration_area: str):
        """Initialize list tool."""
        super().__init__(exploration_area)
        self.path_validator = PathValidator(exploration_area)

    def validate_args(self, **kwargs: Any) -> bool:
        """Validate list arguments."""
        # Directory is optional; defaults to exploration_area
        if "directory" in kwargs:
            directory = kwargs["directory"]
            return isinstance(directory, str)
        return True

    async def execute(
        self,
        directory: Optional[str] = None,
        max_depth: int = 3,
        include_hidden: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """
        List directory contents.
        
        Args:
            directory: Directory to list (defaults to exploration_area root)
            max_depth: Max directory traversal depth
            include_hidden: Whether to include hidden files
            
        Returns:
            ToolResult with directory listing
        """
        try:
            target_dir = directory or self.exploration_area
            validated_path = self.path_validator.validate(target_dir, mode="read")

            if not validated_path.is_dir():
                return ToolResult(
                    success=False, error_message=f"Not a directory: {validated_path}"
                )

            start_time = time.time()

            # Build tree structure
            tree_lines = self._build_tree(validated_path, max_depth, include_hidden)
            content = "\n".join(tree_lines)
            duration = time.time() - start_time

            return ToolResult(
                success=True,
                stdout=content,
                duration_seconds=duration,
                data={
                    "path": str(validated_path),
                    "lines": len(tree_lines),
                    "max_depth": max_depth,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False, error_message=f"List tool error: {e}"
            )

    def _build_tree(
        self,
        path: Path,
        max_depth: int,
        include_hidden: bool,
        current_depth: int = 0,
        prefix: str = "",
    ) -> list[str]:
        """Build tree structure recursively."""
        lines = []

        if current_depth == 0:
            lines.append(str(path) + "/")

        if current_depth >= max_depth:
            return lines

        try:
            entries = sorted(path.iterdir())
        except (PermissionError, OSError):
            return lines

        dirs = [e for e in entries if e.is_dir()]
        files = [e for e in entries if e.is_file()]

        # Filter hidden
        if not include_hidden:
            dirs = [d for d in dirs if not d.name.startswith(".")]
            files = [f for f in files if not f.name.startswith(".")]

        # Process directories first
        for i, dir_path in enumerate(dirs):
            is_last_dir = i == len(dirs) - 1 and len(files) == 0
            connector = "└── " if is_last_dir else "├── "
            lines.append(f"{prefix}{connector}{dir_path.name}/")

            # Recurse
            extension = "    " if is_last_dir else "│   "
            sub_lines = self._build_tree(
                dir_path, max_depth, include_hidden, current_depth + 1, prefix + extension
            )
            lines.extend(sub_lines[1:])  # Skip the repeated directory name

        # Process files
        for i, file_path in enumerate(files):
            is_last = i == len(files) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{file_path.name}")

        return lines


# Convenience function
async def list_directory(
    exploration_area: str,
    directory: Optional[str] = None,
    max_depth: int = 3,
    **kwargs: Any,
) -> ToolResult:
    """Convenience function to list directory."""
    tool = ListTool(exploration_area)
    return await tool.execute(
        directory=directory, max_depth=max_depth, **kwargs
    )
