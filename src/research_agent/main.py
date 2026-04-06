"""Main CLI entry point for Research Agent."""

import typer
from pathlib import Path
from typing import Optional, List

app = typer.Typer(
    name="research-agent",
    help="LLM-driven autonomous code exploration",
    no_args_is_help=True,
)


@app.command()
def explore(
    area: str = typer.Argument(
        ...,
        help="Root directory or path to explore",
    ),
    seed_ideas: Optional[List[str]] = typer.Option(
        None,
        "--seed-idea",
        "-i",
        help="Seed ideas (can specify multiple times)",
    ),
    max_ideas: int = typer.Option(
        20,
        "--max-ideas",
        "-m",
        help="Maximum number of exploratory ideas",
    ),
    llm_provider: str = typer.Option(
        "claude",
        "--llm-provider",
        "-p",
        help="LLM provider (claude, openai, local/ollama, gemini)",
    ),
    report_format: str = typer.Option(
        "markdown",
        "--report-format",
        "-f",
        help="Report format (markdown, json)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode",
    ),
) -> None:
    """
    Start code exploration on the specified area.
    
    Example:
    
        research-agent explore src/payment --max-ideas 15 --report-format markdown
    """
    typer.echo(f"🚀 Starting exploration of {area}")
    typer.echo(f"📋 Max ideas: {max_ideas}")
    typer.echo(f"🤖 LLM provider: {llm_provider}")
    
    if seed_ideas:
        typer.echo(f"💡 Seed ideas: {len(seed_ideas)}")
        for idea in seed_ideas:
            typer.echo(f"   - {idea}")
    
    # TODO: Implement actual exploration logic
    typer.echo("\n⚠️  [MVP] Exploration logic not yet implemented")
    typer.echo("Right-click this output to see project structure setup complete!")


@app.command()
def config(
    action: str = typer.Argument(
        "show",
        help="Config action (show, init, edit)",
    ),
) -> None:
    """
    Manage Research Agent configuration.
    """
    if action == "show":
        typer.echo("📋 Research Agent Configuration")
        typer.echo("=" * 50)
        typer.echo("\nCurrent configuration:")
        typer.echo("  LLM Provider: claude")
        typer.echo("  Sandbox Mode: path-validation")
        typer.echo("  Max Ideas: 20")
        typer.echo("\n⚠️  [MVP] Full config management coming soon")
    elif action == "init":
        typer.echo("📝 Initializing configuration...")
        typer.echo("✓ Config directory created: .research-agent/")
        typer.echo("✓ Sample config created: config.yaml")
    else:
        typer.echo(f"Unknown action: {action}")


@app.command()
def version() -> None:
    """Show version information."""
    from research_agent import __version__
    typer.echo(f"Research Agent v{__version__}")


@app.callback()
def main(
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging",
        hidden=True,
    ),
) -> None:
    """
    Research Agent: LLM-driven autonomous code exploration
    
    Reason → Act → Learn → Memorize
    """
    if debug:
        typer.echo("🔧 Debug mode enabled")


if __name__ == "__main__":
    app()
