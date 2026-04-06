"""SQLAlchemy database models for persistent storage."""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    JSON,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session, sessionmaker

from research_agent.core.models import (
    IdeaStatus,
    MemoryType,
    RunStatus,
    ToolName,
)
from research_agent.core.config import settings

Base = declarative_base()


class ResearchRunModel(Base):
    """Database model for ResearchRun."""

    __tablename__ = "research_runs"

    id = Column(String(64), primary_key=True)
    area_roots = Column(JSON)  # List of root paths
    area_include_patterns = Column(JSON)  # Include patterns
    area_exclude_patterns = Column(JSON)  # Exclude patterns
    
    user_seed_ideas = Column(JSON)  # List of seed ideas
    
    status = Column(SQLEnum(RunStatus), default=RunStatus.CREATED)
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    token_budget = Column(Integer, default=100000)
    tokens_used = Column(Integer, default=0)
    tool_call_budget = Column(Integer, default=200)
    tool_calls_used = Column(Integer, default=0)
    wall_clock_budget_seconds = Column(Integer, default=3600)
    
    error_message = Column(Text, nullable=True)
    
    # Relationships
    ideas = relationship("ExploratoryIdeaModel", back_populates="run")
    tool_traces = relationship("ToolTraceModel", back_populates="run")
    findings = relationship("FindingModel", back_populates="run")
    memories = relationship("MemoryModel", back_populates="run")
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tokens_used": self.tokens_used,
            "tool_calls_used": self.tool_calls_used,
        }


class ExploratoryIdeaModel(Base):
    """Database model for ExploratoryIdea."""

    __tablename__ = "exploratory_ideas"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("research_runs.id"), nullable=False)
    parent_id = Column(String(64), nullable=True)
    
    title = Column(String(256))
    description = Column(Text)
    status = Column(SQLEnum(IdeaStatus), default=IdeaStatus.QUEUED)
    
    priority = Column(Integer, default=3)
    confidence = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    block_reason = Column(Text, nullable=True)
    
    # Relationships
    run = relationship("ResearchRunModel", back_populates="ideas")
    findings = relationship("FindingModel", back_populates="idea")
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value if self.status else None,
            "priority": self.priority,
            "confidence": self.confidence,
        }


class FindingModel(Base):
    """Database model for Finding."""

    __tablename__ = "findings"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("research_runs.id"), nullable=False)
    idea_id = Column(String(64), ForeignKey("exploratory_ideas.id"), nullable=False)
    
    description = Column(Text)
    code_locations = Column(JSON)  # List of code locations
    confidence = Column(Float, default=0.5)
    
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    run = relationship("ResearchRunModel", back_populates="findings")
    idea = relationship("ExploratoryIdeaModel", back_populates="findings")
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "description": self.description,
            "confidence": self.confidence,
            "code_locations": self.code_locations,
        }


class ToolTraceModel(Base):
    """Database model for ToolTrace."""

    __tablename__ = "tool_traces"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("research_runs.id"), nullable=False)
    idea_id = Column(String(64), nullable=True)
    
    tool_name = Column(String(64))
    tool_input = Column(JSON)
    
    success = Column(Boolean, default=True)
    stdout = Column(Text)
    stderr = Column(Text)
    
    duration_seconds = Column(Float, default=0.0)
    tokens_used = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    run = relationship("ResearchRunModel", back_populates="tool_traces")
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MemoryModel(Base):
    """Database model for Memory."""

    __tablename__ = "memories"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("research_runs.id"), nullable=True)
    
    memory_type = Column(SQLEnum(MemoryType), default=MemoryType.PATTERN)
    description = Column(Text)
    confidence = Column(Float, default=0.5)
    
    source_idea_id = Column(String(64), nullable=True)
    source_tool_trace_id = Column(String(64), nullable=True)
    
    persist = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.now)
    last_used_at = Column(DateTime, nullable=True)
    usage_count = Column(Integer, default=0)
    
    # Relationships
    run = relationship("ResearchRunModel", back_populates="memories")
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "type": self.memory_type.name if self.memory_type else None,
            "description": self.description,
            "confidence": self.confidence,
            "persist": self.persist,
        }


class DatabaseManager:
    """Manager for database operations and session handling."""

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database manager.
        
        Args:
            database_url: SQLite URL; if None, uses settings.storage.database_url
        """
        self.database_url = database_url or settings.storage.database_url
        self.engine = create_engine(self.database_url, connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def init_db(self) -> None:
        """Initialize database schema."""
        Base.metadata.create_all(bind=self.engine)
        print(f"✓ Database initialized: {self.database_url}")
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()
    
    def save_run(self, run_model: ResearchRunModel) -> None:
        """Save a research run to database."""
        session = self.get_session()
        try:
            session.add(run_model)
            session.commit()
        finally:
            session.close()
    
    def load_run(self, run_id: str) -> Optional[ResearchRunModel]:
        """Load a research run from database."""
        session = self.get_session()
        try:
            return session.query(ResearchRunModel).filter(
                ResearchRunModel.id == run_id
            ).first()
        finally:
            session.close()
    
    def list_runs(self, limit: int = 100) -> List[ResearchRunModel]:
        """List recent research runs."""
        session = self.get_session()
        try:
            return session.query(ResearchRunModel).order_by(
                ResearchRunModel.created_at.desc()
            ).limit(limit).all()
        finally:
            session.close()
    
    def save_idea(self, idea_model: ExploratoryIdeaModel) -> None:
        """Save an exploratory idea."""
        session = self.get_session()
        try:
            session.add(idea_model)
            session.commit()
        finally:
            session.close()
    
    def save_finding(self, finding_model: FindingModel) -> None:
        """Save a finding."""
        session = self.get_session()
        try:
            session.add(finding_model)
            session.commit()
        finally:
            session.close()
    
    def save_tool_trace(self, trace_model: ToolTraceModel) -> None:
        """Save a tool trace."""
        session = self.get_session()
        try:
            session.add(trace_model)
            session.commit()
        finally:
            session.close()
    
    def save_memory(self, memory_model: MemoryModel) -> None:
        """Save a memory."""
        session = self.get_session()
        try:
            session.add(memory_model)
            session.commit()
        finally:
            session.close()
    
    def get_run_ideas(self, run_id: str) -> List[ExploratoryIdeaModel]:
        """Get all ideas for a run."""
        session = self.get_session()
        try:
            return session.query(ExploratoryIdeaModel).filter(
                ExploratoryIdeaModel.run_id == run_id
            ).all()
        finally:
            session.close()
    
    def get_idea_findings(self, idea_id: str) -> List[FindingModel]:
        """Get all findings for an idea."""
        session = self.get_session()
        try:
            return session.query(FindingModel).filter(
                FindingModel.idea_id == idea_id
            ).all()
        finally:
            session.close()
    
    def get_run_memories(self, run_id: str) -> List[MemoryModel]:
        """Get all memories for a run."""
        session = self.get_session()
        try:
            return session.query(MemoryModel).filter(
                MemoryModel.run_id == run_id
            ).all()
        finally:
            session.close()
