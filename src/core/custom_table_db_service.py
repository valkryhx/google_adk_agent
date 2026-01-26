import json
from datetime import datetime
from typing import Optional, List, Any

from google.adk.sessions import Session, BaseSessionService
from google.adk.sessions.base_session_service import ListSessionsResponse
from google.adk.events import Event as AdkEvent

# SQLAlchemy Dependencies
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload
from sqlalchemy.orm import registry as _registry

# ==========================================
# Dynamic Model Builder
# ==========================================
def define_orm_classes(session_tbl_name: str, event_tbl_name: str):
    """
    Dynamically generate ORM classes based on passed table names.
    :param session_tbl_name: The name of the session table.
    :param event_tbl_name: The name of the event table.
    :return: Tuple of (Base, DbSession, DbEvent) classes.
    """
    # Use independent registry to prevent metadata conflict between different Service instances
    mapper_registry = _registry()
    
    class Base(DeclarativeBase):
        registry = mapper_registry

    # --- 1. Define Session Table ---
    class DbSession(Base):
        # [User Defined] Fully determined by the string you pass
        __tablename__ = session_tbl_name

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        
        # Indexing for speed
        app_name: Mapped[str] = mapped_column(String(255), index=True)
        user_id: Mapped[str] = mapped_column(String(255), index=True)
        session_id: Mapped[str] = mapped_column(String(255), index=True)
        
        # Store Session State (Supports Update operations)
        session_metadata: Mapped[str] = mapped_column(Text, default="{}")

        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
        updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        # Relationships
        events: Mapped[List["DbEvent"]] = relationship(
            "DbEvent", back_populates="session", cascade="all, delete-orphan"
        )

    # --- 2. Define Event Table ---
    class DbEvent(Base):
        # [User Defined] Fully determined by the string you pass
        __tablename__ = event_tbl_name

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        
        # [Core Difficulty] Dynamic Foreign Key: Must point to id column of session_tbl_name
        session_internal_id: Mapped[int] = mapped_column(
            ForeignKey(f"{session_tbl_name}.id", ondelete="CASCADE"), index=True
        )
        
        session: Mapped["DbSession"] = relationship("DbSession", back_populates="events")

        invocation_id: Mapped[str] = mapped_column(String(255), nullable=True)
        role: Mapped[str] = mapped_column(String(50), nullable=True)
        event_json: Mapped[str] = mapped_column(Text)
        timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    return Base, DbSession, DbEvent

# ==========================================
# Service Implementation
# ==========================================
class FullyCustomDbService(BaseSessionService):
    def __init__(
        self, 
        db_url: str, 
        session_table_name: str = "adk_sessions", 
        event_table_name: str = "adk_events"
    ):
        """
        :param db_url: Database connection string (e.g. sqlite+aiosqlite:///file.db)
        :param session_table_name: User defined Session table name (full name)
        :param event_table_name: User defined Event table name (full name)
        """
        self.engine = create_async_engine(
            db_url, 
            echo=False, 
            pool_recycle=3600
        )
        self.async_session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        
        # Dynamically create classes
        self.Base, self.DbSession, self.DbEvent = define_orm_classes(
            session_table_name, 
            event_table_name
        )

    async def init_db(self):
        """Create database tables based on dynamically defined table names"""
        async with self.engine.begin() as conn:
            await conn.run_sync(self.Base.metadata.create_all)

    async def get_session(self, app_name: str, user_id: str, session_id: str) -> Optional[Session]:
        async with self.async_session_factory() as db:
            # Use strict isolation level or explicit locking if supported/needed.
            # Here we follow the discussion's "Scheme A" using with_for_update() to prevent race conditions.
            async with db.begin():
                stmt = select(self.DbSession).where(
                    self.DbSession.app_name == app_name,
                    self.DbSession.user_id == user_id,
                    self.DbSession.session_id == session_id
                ).options(selectinload(self.DbSession.events))
                
                # Adding with_for_update for concurrency safety
                stmt = stmt.with_for_update()
                
                result = await db.execute(stmt)
                db_session = result.scalar_one_or_none()

                if not db_session:
                    return None

                # Restore Session
                adk_session = Session(app_name=app_name, user_id=user_id, id=session_id)
                
                # [Checkpoint 1] Restore Real-time State (Support Update operations)
                if db_session.session_metadata:
                    try:
                        if hasattr(adk_session, 'state'):
                            adk_session.state = json.loads(db_session.session_metadata)
                    except Exception as e:
                        print(f"State load error: {e}")

                # Restore Events
                # Sort to ensure order
                sorted_events = sorted(db_session.events, key=lambda e: e.id)
                reconstructed_events = []
                for db_evt in sorted_events:
                    try:
                        evt_dict = json.loads(db_evt.event_json)
                        reconstructed_events.append(AdkEvent.model_validate(evt_dict))
                    except Exception:
                        pass
                
                adk_session.events = reconstructed_events
            return adk_session

    async def create_session(self, app_name: str, user_id: str, session_id: str) -> Session:
        """Create a new session if not exists, or return exception if exists (or verify)"""
        existing = await self.get_session(app_name, user_id, session_id)
        if existing:
            # Depending on logic, we might return existing or raise error. 
            # ADK InMemory implementation simply overwrites or returns new object? 
            # Usually create_session means fresh start.
            return existing
        
        session = Session(app_name=app_name, user_id=user_id, id=session_id)
        await self.save_session(session)
        return session

    async def save_session(self, session: Session):
        """
        Full sync save (Supports Update and Rewind)
        """
        async with self.async_session_factory() as db:
            async with db.begin():
                stmt = select(self.DbSession).where(
                    self.DbSession.app_name == session.app_name,
                    self.DbSession.user_id == session.user_id,
                    self.DbSession.session_id == session.id
                ).options(selectinload(self.DbSession.events))
                
                result = await db.execute(stmt)
                db_session = result.scalar_one_or_none()

                if not db_session:
                    db_session = self.DbSession(
                        app_name=session.app_name, 
                        user_id=session.user_id, 
                        session_id=session.id
                    )
                    db.add(db_session)
                
                # [Checkpoint 2] Save Real-time Updated State
                db_session.updated_at = datetime.utcnow()
                if hasattr(session, 'state'):
                    # Overwrite functionality
                    db_session.session_metadata = json.dumps(session.state or {}, ensure_ascii=False)

                # [Checkpoint 3] Handle Event List (Support Rewind)
                # Reconstruct Event list, SQLAlchemy handles Diff automatically (deleting orphans)
                new_db_events = []
                for evt in session.events:
                    evt_dict = evt.model_dump(mode='json')
                    evt_json = json.dumps(evt_dict, ensure_ascii=False)
                    
                    role = 'unknown'
                    if hasattr(evt, 'role'): role = evt.role
                    if hasattr(evt, 'role'): role = evt.role
                    elif hasattr(evt, 'author'): role = evt.author
                    elif hasattr(evt, 'content') and hasattr(evt.content, 'role'):
                        role = evt.content.role

                    new_db_events.append(self.DbEvent(
                        invocation_id=getattr(evt, 'invocation_id', None),
                        role=role,
                        event_json=evt_json
                    ))
                
                # Assignment triggers cascade logic
                db_session.events = new_db_events

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        async with self.async_session_factory() as db:
            async with db.begin():
                stmt = select(self.DbSession).where(
                    self.DbSession.app_name == app_name,
                    self.DbSession.user_id == user_id,
                    self.DbSession.session_id == session_id
                )
                result = await db.execute(stmt)
                db_session = result.scalar_one_or_none()
                
                if db_session:
                    await db.delete(db_session)

    async def list_sessions(self, *, app_name: str, user_id: Optional[str] = None) -> ListSessionsResponse:
        async with self.async_session_factory() as db:
            async with db.begin():
                stmt = select(self.DbSession).where(self.DbSession.app_name == app_name)
                
                if user_id is not None:
                    stmt = stmt.where(self.DbSession.user_id == user_id)
                
                result = await db.execute(stmt)
                db_sessions = result.scalars().all()
                
                sessions_list = []
                for db_s in db_sessions:
                    # Reconstruct session without events (lightweight)
                    adk_session = Session(
                        app_name=db_s.app_name, 
                        user_id=db_s.user_id, 
                        id=db_s.session_id
                    )
                    
                    # Restore State if available
                    if db_s.session_metadata:
                        try:
                            if hasattr(adk_session, 'state'):
                                adk_session.state = json.loads(db_s.session_metadata)
                        except Exception as e:
                            print(f"State load error in list_sessions: {e}")
                            
                    sessions_list.append(adk_session)
                    
                return ListSessionsResponse(sessions=sessions_list)

    async def append_event(self, session: Session, event: AdkEvent) -> AdkEvent:
        # 1. Base implementation (Updates in-memory session.state and session.events)
        await super().append_event(session, event)
        
        # 2. DB Persistence
        async with self.async_session_factory() as db:
            async with db.begin():
                stmt = select(self.DbSession).where(
                    self.DbSession.app_name == session.app_name,
                    self.DbSession.user_id == session.user_id,
                    self.DbSession.session_id == session.id
                ).options(selectinload(self.DbSession.events))
                result = await db.execute(stmt)
                db_session = result.scalar_one_or_none()
                
                if db_session:
                    # Create DbEvent
                    evt_dict = event.model_dump(mode='json')
                    evt_json = json.dumps(evt_dict, ensure_ascii=False)
                    
                    role = 'unknown'
                    if hasattr(event, 'role'): role = event.role
                    elif hasattr(event, 'author'): role = event.author
                    elif hasattr(event, 'content') and hasattr(event.content, 'role'):
                        role = event.content.role

                    new_db_event = self.DbEvent(
                        invocation_id=getattr(event, 'invocation_id', None),
                        role=role,
                        event_json=evt_json,
                        timestamp=datetime.utcnow()
                    )
                    
                    db_session.events.append(new_db_event)
                    
                    # Update Session Metadata (State might have changed via super().append_event)
                    db_session.updated_at = datetime.utcnow()
                    if hasattr(session, 'state'):
                        db_session.session_metadata = json.dumps(session.state or {}, ensure_ascii=False)
        
        return event

