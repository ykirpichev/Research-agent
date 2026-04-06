"""Search tool: Find patterns in codebase."""

import asyncio
import time
from typing import Any, Optional

from research_agent.core.config import settings
from research_agent.tools import PermissionError, TimeoutError, ToolResult, SandboxTool
from research_agent.tools.sandbox import ProcessSandbox


class SearchTool(SandboxTool):
    """Search files using ripgrep (rg)."""

    def __init__(self, exploration_area: str):
        """Initialize search tool."""
        super().__init__(exploration_area)
        self.sandbox = ProcessSandbox(exploration_area)

    def validate_args(self, **kwargs: Any) -> bool:
        """Validate search arguments."""
        if "pattern" not in kwargs:
            return False
        pattern = kwargs["pattern"]
        if not isinstance(pattern, str) or len(pattern) == 0:
            return False
        return True

    async def execute(
        self,
        pattern: str,
        file_type: Optional[str] = None,
        max_results: Optional[int] = None,
        case_insensitive: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Search for pattern in codebase.
        
        Args:
            pattern: Search pattern (regex)
            file_type: File type filter (e.g., 'py', 'go', 'ts')
            max_results: Max results to return
            case_insensitive: Case-insensitive search
            
        Returns:
            ToolResult with search results
        """
        if not self.validate_args(pattern=pattern):
            return ToolResult(
                success=False, error_message="Invalid search arguments"
            )

        # Build ripgrep command
        cmd = ["rg"]
        
        # Add file type filter if specified
        if file_type:
            cmd.extend(["--type", file_type])

        # Add case flag
        if case_insensitive:
            cmd.append("-i")

        # Add the pattern
        cmd.append(pattern)

        # Add search root
        cmd.append(str(self.exploration_area))

        # Add result limits
        max_res = max_results or settings.sandbox.max_search_results
        cmd.extend(["--max-count", str(max_res)])

        # Format options
        cmd.extend([
            "--with-filename",
            "--line-number",
            "--color=never",
        ])

        try:
            start_time = time.time()
            result = self.sandbox.run_command(
                cmd,
                timeout_seconds=settings.sandbox.tool_timeout_seconds,
            )
            duration = time.time() - start_time

            if result["success"] or result["returncode"] == 1:  # 1 = no matches
                # Parse results
                lines = result["stdout"].strip().split("\n") if result["stdout"] else []
                matches = len([l for l in lines if l])

                return ToolResult(
                    success=True,
                    stdout=result["stdout"],
                    stderr=result["stderr"],
                    duration_seconds=duration,
                    data={"matches": matches, "results": lines},
                )
            else:
                return ToolResult(
                    success=False,
                    stderr=result["stderr"],
                    duration_seconds=duration,
                    error_message=f"Search failed: {result['stderr']}",
                )

        except TimeoutError as e:
            return ToolResult(
                success=False,
                error_message=str(e),
                duration_seconds=settings.sandbox.tool_timeout_seconds,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error_message=f"Search tool error: {e}",
            )


# Convenience function
async def search(
    exploration_area: str,
    pattern: str,
    file_type: Optional[str] = None,
    **kwargs: Any,
) -> ToolResult:
    """Convenience function to run search."""
    tool = SearchTool(exploration_area)
    return await tool.execute(pattern=pattern, file_type=file_type, **kwargs)
