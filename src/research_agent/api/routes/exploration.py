"""FastAPI REST API routes for research agent."""

import logging
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from research_agent.core.models import (
    ResearchRun,
    ExplorationArea,
    RunStatus,
)
from research_agent.storage import DatabaseManager, ResearchRunModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/research", tags=["research"])

# Initialize database
db_manager = DatabaseManager()


# ========== Pydantic Models for API Requests/Responses ==========


class ExplorationRequest(BaseModel):
    """Request to start a new code exploration."""

    roots: List[str] = Field(..., description="Root directories to explore")
    include_patterns: Optional[List[str]] = Field(
        None, description="File patterns to include (e.g., *.py)"
    )
    exclude_patterns: Optional[List[str]] = Field(
        None, description="File patterns to exclude (e.g., __pycache__)"
    )
    seed_ideas: Optional[List[str]] = Field(
        None, description="Initial exploratory ideas"
    )
    max_ideas: Optional[int] = Field(
        20, description="Maximum exploratory ideas to generate"
    )
    llm_provider: Optional[str] = Field(
        "claude", description="LLM provider: claude, openai, local, gemini"
    )


class ExplorationResponse(BaseModel):
    """Response to exploration startup."""

    run_id: str = Field(..., description="Unique research run ID")
    status: str = Field("created", description="Current run status")
    message: str = Field(..., description="Status message")


class RunStatusResponse(BaseModel):
    """Response with run status and progress."""

    run_id: str
    status: str
    created_at: str
    completed_at: Optional[str]
    ideas_count: int
    ideas_explored: int
    findings_count: int
    tokens_used: int
    tool_calls_used: int


# ========== Routes ==========


@router.post("/explore", response_model=ExplorationResponse)
async def start_exploration(
    request: ExplorationRequest,
    background_tasks: BackgroundTasks,
) -> ExplorationResponse:
    """
    Start a new code exploration.
    
    Args:
        request: Exploration configuration
        background_tasks: Background task queue
        
    Returns:
        ExplorationResponse with run ID
    """
    try:
        # Create exploration area
        area = ExplorationArea(
            roots=request.roots,
            include_patterns=request.include_patterns or [],
            exclude_patterns=request.exclude_patterns or [],
        )
        
        # Create research run
        run = ResearchRun(
            id=str(uuid4()),
            area=area,
            user_seed_ideas=request.seed_ideas or [],
        )
        
        # Save to database
        run_model = _convert_run_to_model(run)
        db_manager.save_run(run_model)
        
        logger.info(f"Started exploration run: {run.id}")
        
        # TODO: Queue background task to execute exploration
        # This would call orchestrator.execute_exploration()
        
        return ExplorationResponse(
            run_id=run.id,
            status="created",
            message=f"Exploration started for {len(request.roots)} root(s)",
        )
        
    except Exception as e:
        logger.error(f"Error starting exploration: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs/{run_id}/status", response_model=RunStatusResponse)
async def get_run_status(run_id: str) -> RunStatusResponse:
    """
    Get the status of a research run.
    
    Args:
        run_id: Research run ID
        
    Returns:
        Current status and progress
    """
    try:
        run_model = db_manager.load_run(run_id)
        if not run_model:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        
        # Get counts
        ideas = db_manager.get_run_ideas(run_id)
        explored_count = len([i for i in ideas if i.status.value in ["explored", "blocked"]])
        findings = db_manager.get_run_memories(run_id)  # Findings count
        
        return RunStatusResponse(
            run_id=run_id,
            status=run_model.status.value if run_model.status else "unknown",
            created_at=run_model.created_at.isoformat() if run_model.created_at else "",
            completed_at=run_model.completed_at.isoformat() if run_model.completed_at else None,
            ideas_count=len(ideas),
            ideas_explored=explored_count,
            findings_count=len(findings),
            tokens_used=run_model.tokens_used or 0,
            tool_calls_used=run_model.tool_calls_used or 0,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading run status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs")
async def list_runs(limit: int = 10) -> dict:
    """
    List recent research runs.
    
    Args:
        limit: Maximum runs to return
        
    Returns:
        Dictionary with runs list
    """
    try:
        runs = db_manager.list_runs(limit=limit)
        return {
            "runs": [
                {
                    "run_id": r.id,
                    "status": r.status.value if r.status else "unknown",
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                }
                for r in runs
            ]
        }
    except Exception as e:
        logger.error(f"Error listing runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/ideas")
async def get_run_ideas(run_id: str) -> dict:
    """
    Get all ideas for a research run.
    
    Args:
        run_id: Research run ID
        
    Returns:
        Dictionary with ideas list
    """
    try:
        run_model = db_manager.load_run(run_id)
        if not run_model:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        
        ideas = db_manager.get_run_ideas(run_id)
        return {
            "ideas": [i.to_dict() for i in ideas]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading run ideas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/findings")
async def get_idea_findings(run_id: str, idea_id: Optional[str] = None) -> dict:
    """
    Get findings for a run or specific idea.
    
    Args:
        run_id: Research run ID
        idea_id: Optional idea ID to filter findings
        
    Returns:
        Dictionary with findings list
    """
    try:
        run_model = db_manager.load_run(run_id)
        if not run_model:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        
        if idea_id:
            findings = db_manager.get_idea_findings(idea_id)
        else:
            # Get all findings for the run
            ideas = db_manager.get_run_ideas(run_id)
            findings = []
            for idea in ideas:
                findings.extend(db_manager.get_idea_findings(idea.id))
        
        return {
            "findings": [f.to_dict() for f in findings]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading findings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/memories")
async def get_run_memories(run_id: str) -> dict:
    """
    Get learned memories for a research run.
    
    Args:
        run_id: Research run ID
        
    Returns:
        Dictionary with memories list
    """
    try:
        run_model = db_manager.load_run(run_id)
        if not run_model:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        
        memories = db_manager.get_run_memories(run_id)
        return {
            "memories": [m.to_dict() for m in memories]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Health Check Routes ==========


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "research-agent-api",
        "version": "0.1.0",
    }


# ========== Helpers ==========


def _convert_run_to_model(run: ResearchRun) -> ResearchRunModel:
    """Convert ResearchRun to database model."""
    return ResearchRunModel(
        id=run.id,
        area_roots=[str(r) for r in run.area.roots],
        area_include_patterns=run.area.include_patterns,
        area_exclude_patterns=run.area.exclude_patterns,
        user_seed_ideas=run.user_seed_ideas,
        status=run.status,
        token_budget=run.token_budget,
        tokens_used=run.tokens_used,
        tool_call_budget=run.tool_call_budget,
        tool_calls_used=run.tool_calls_used,
    )
