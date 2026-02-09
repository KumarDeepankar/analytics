"""
Database module for dashboard persistence.

Uses SQLite with SQLAlchemy async for local storage.
"""

import os
import json
from datetime import datetime
from typing import Optional, List, Any, Union
from contextlib import asynccontextmanager

from sqlalchemy import Column, String, Text, DateTime, Boolean, LargeBinary, Integer, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from pydantic import BaseModel, ConfigDict, Field

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./storage/dashboards.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


# SQLAlchemy Models

class DashboardModel(Base):
    """Dashboard database model."""
    __tablename__ = "dashboards"

    id = Column(String(50), primary_key=True)
    title = Column(String(255), nullable=False)
    charts = Column(Text, nullable=False, default="[]")  # JSON array of charts
    layout = Column(Text, nullable=False, default="[]")  # JSON array of layout
    messages = Column(Text, nullable=False, default="[]")  # JSON array of messages
    filters = Column(Text, nullable=False, default="[]")  # JSON array of saved filters
    images = Column(Text, nullable=False, default="[]")  # JSON array of image configs
    presentation = Column(Text, nullable=True)  # JSON presentation data
    dashboard_theme = Column(String(50), default='light')
    is_published = Column(Boolean, default=False)
    share_id = Column(String(50), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UploadedImageModel(Base):
    """Uploaded image stored as BLOB in the database."""
    __tablename__ = "uploaded_images"

    id = Column(String(50), primary_key=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Pydantic Models

class ChartConfigSchema(BaseModel):
    """Chart configuration schema."""
    model_config = ConfigDict(extra='allow')

    id: str
    type: str
    title: str
    dataSource: str
    xField: Optional[str] = None
    yField: Optional[str] = None
    seriesField: Optional[str] = None
    additionalFields: Optional[List[dict]] = None
    aggregation: Optional[str] = "count"
    filters: List[dict] = Field(default_factory=list)
    appliedFilters: Optional[dict] = None
    options: Optional[dict] = None
    visualSettings: Optional[dict] = None
    xAxisSettings: Optional[dict] = None
    yAxisSettings: Optional[dict] = None
    viewMode: Optional[str] = None


class LayoutItemSchema(BaseModel):
    """Layout item schema."""
    i: str
    x: int
    y: int
    w: int
    h: int
    minW: Optional[int] = None
    minH: Optional[int] = None


class MessageSchema(BaseModel):
    """Chat message schema."""
    id: str
    role: str
    content: str
    timestamp: str
    charts: Optional[List[ChartConfigSchema]] = None
    sources: Optional[List[dict]] = None
    error: Optional[str] = None


class FilterSchema(BaseModel):
    """Filter schema for saved filters."""
    id: str
    field: str
    operator: str
    value: Union[str, int, float, List[str], List[int], List[float]]  # Can be string, number, or array
    source: Optional[str] = None


class ImageConfigSchema(BaseModel):
    """Image configuration schema."""
    model_config = ConfigDict(extra='allow')

    id: str
    type: str = 'image'
    title: str
    url: str
    alt: Optional[str] = None
    objectFit: Optional[str] = 'cover'


class DashboardSchema(BaseModel):
    """Dashboard schema for API."""
    id: str
    title: str
    charts: List[ChartConfigSchema] = Field(default_factory=list)
    layout: List[LayoutItemSchema] = Field(default_factory=list)
    messages: List[MessageSchema] = Field(default_factory=list)
    filters: List[FilterSchema] = Field(default_factory=list)  # Saved filters
    images: List[ImageConfigSchema] = Field(default_factory=list)
    presentation: Optional[dict] = None  # JSON presentation data
    dashboard_theme: str = 'light'
    is_published: bool = False
    share_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class DashboardCreateSchema(BaseModel):
    """Schema for creating a dashboard."""
    id: str
    title: str
    charts: List[dict] = Field(default_factory=list)
    layout: List[dict] = Field(default_factory=list)
    messages: List[dict] = Field(default_factory=list)
    filters: List[dict] = Field(default_factory=list)
    images: List[dict] = Field(default_factory=list)
    presentation: Optional[dict] = None
    dashboard_theme: str = 'light'


class DashboardUpdateSchema(BaseModel):
    """Schema for updating a dashboard."""
    title: Optional[str] = None
    charts: Optional[List[dict]] = None
    layout: Optional[List[dict]] = None
    messages: Optional[List[dict]] = None
    filters: Optional[List[dict]] = None
    images: Optional[List[dict]] = None
    presentation: Optional[dict] = None
    dashboard_theme: Optional[str] = None


class PublishResponseSchema(BaseModel):
    """Response for publishing a dashboard."""
    share_id: str
    share_url: str


# Database initialization

async def init_db():
    """Initialize the database and create tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run migrations for existing tables (add filters column if missing)
    await run_migrations()


async def run_migrations():
    """Run database migrations for schema changes."""
    from sqlalchemy import text

    async with async_session() as session:
        try:
            # Check if filters column exists
            result = await session.execute(
                text("PRAGMA table_info(dashboards)")
            )
            columns = [row[1] for row in result.fetchall()]

            if 'filters' not in columns:
                # Add filters column
                await session.execute(
                    text("ALTER TABLE dashboards ADD COLUMN filters TEXT DEFAULT '[]'")
                )
                await session.commit()
                print("Migration: Added 'filters' column to dashboards table")

            if 'dashboard_theme' not in columns:
                await session.execute(
                    text("ALTER TABLE dashboards ADD COLUMN dashboard_theme VARCHAR(50) DEFAULT 'light'")
                )
                await session.commit()
                print("Migration: Added 'dashboard_theme' column to dashboards table")

            if 'images' not in columns:
                await session.execute(
                    text("ALTER TABLE dashboards ADD COLUMN images TEXT DEFAULT '[]'")
                )
                await session.commit()
                print("Migration: Added 'images' column to dashboards table")

            if 'presentation' not in columns:
                await session.execute(
                    text("ALTER TABLE dashboards ADD COLUMN presentation TEXT")
                )
                await session.commit()
                print("Migration: Added 'presentation' column to dashboards table")
        except Exception as e:
            print(f"Migration check/run error (may be safe to ignore): {e}")


@asynccontextmanager
async def get_db_session():
    """Get a database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Database operations

async def get_all_dashboards() -> List[DashboardSchema]:
    """Get all dashboards."""
    async with get_db_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(DashboardModel).order_by(DashboardModel.updated_at.desc()))
        dashboards = result.scalars().all()

        return [
            DashboardSchema(
                id=d.id,
                title=d.title,
                charts=json.loads(d.charts),
                layout=json.loads(d.layout),
                messages=json.loads(d.messages),
                filters=json.loads(d.filters) if d.filters else [],
                images=json.loads(d.images) if d.images else [],
                presentation=json.loads(d.presentation) if d.presentation else None,
                dashboard_theme=d.dashboard_theme or 'light',
                is_published=d.is_published,
                share_id=d.share_id,
                created_at=d.created_at.isoformat() if d.created_at else None,
                updated_at=d.updated_at.isoformat() if d.updated_at else None,
            )
            for d in dashboards
        ]


async def get_dashboard(dashboard_id: str) -> Optional[DashboardSchema]:
    """Get a dashboard by ID."""
    async with get_db_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(DashboardModel).where(DashboardModel.id == dashboard_id)
        )
        d = result.scalar_one_or_none()

        if not d:
            return None

        return DashboardSchema(
            id=d.id,
            title=d.title,
            charts=json.loads(d.charts),
            layout=json.loads(d.layout),
            messages=json.loads(d.messages),
            filters=json.loads(d.filters) if d.filters else [],
            images=json.loads(d.images) if d.images else [],
            presentation=json.loads(d.presentation) if d.presentation else None,
            dashboard_theme=d.dashboard_theme or 'light',
            is_published=d.is_published,
            share_id=d.share_id,
            created_at=d.created_at.isoformat() if d.created_at else None,
            updated_at=d.updated_at.isoformat() if d.updated_at else None,
        )


async def get_dashboard_by_share_id(share_id: str) -> Optional[DashboardSchema]:
    """Get a published dashboard by share ID."""
    async with get_db_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(DashboardModel).where(
                DashboardModel.share_id == share_id,
                DashboardModel.is_published == True
            )
        )
        d = result.scalar_one_or_none()

        if not d:
            return None

        return DashboardSchema(
            id=d.id,
            title=d.title,
            charts=json.loads(d.charts),
            layout=json.loads(d.layout),
            messages=json.loads(d.messages),
            filters=json.loads(d.filters) if d.filters else [],
            images=json.loads(d.images) if d.images else [],
            presentation=json.loads(d.presentation) if d.presentation else None,
            dashboard_theme=d.dashboard_theme or 'light',
            is_published=d.is_published,
            share_id=d.share_id,
            created_at=d.created_at.isoformat() if d.created_at else None,
            updated_at=d.updated_at.isoformat() if d.updated_at else None,
        )


async def create_dashboard(data: DashboardCreateSchema) -> DashboardSchema:
    """Create a new dashboard."""
    async with get_db_session() as session:
        dashboard = DashboardModel(
            id=data.id,
            title=data.title,
            charts=json.dumps(data.charts),
            layout=json.dumps(data.layout),
            messages=json.dumps(data.messages),
            filters=json.dumps(data.filters),
            images=json.dumps(data.images),
            presentation=json.dumps(data.presentation) if data.presentation else None,
            dashboard_theme=data.dashboard_theme,
        )
        session.add(dashboard)
        await session.flush()

        return DashboardSchema(
            id=dashboard.id,
            title=dashboard.title,
            charts=data.charts,
            layout=data.layout,
            messages=data.messages,
            filters=data.filters,
            images=data.images,
            presentation=data.presentation,
            dashboard_theme=data.dashboard_theme,
            is_published=False,
            share_id=None,
            created_at=dashboard.created_at.isoformat() if dashboard.created_at else None,
            updated_at=dashboard.updated_at.isoformat() if dashboard.updated_at else None,
        )


async def update_dashboard(dashboard_id: str, data: DashboardUpdateSchema) -> Optional[DashboardSchema]:
    """Update an existing dashboard."""
    async with get_db_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(DashboardModel).where(DashboardModel.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            return None

        if data.title is not None:
            dashboard.title = data.title
        if data.charts is not None:
            dashboard.charts = json.dumps(data.charts)
        if data.layout is not None:
            dashboard.layout = json.dumps(data.layout)
        if data.messages is not None:
            dashboard.messages = json.dumps(data.messages)
        if data.filters is not None:
            dashboard.filters = json.dumps(data.filters)
        if data.images is not None:
            dashboard.images = json.dumps(data.images)
        if data.presentation is not None:
            dashboard.presentation = json.dumps(data.presentation)
        if data.dashboard_theme is not None:
            dashboard.dashboard_theme = data.dashboard_theme

        dashboard.updated_at = datetime.utcnow()
        await session.flush()

        return DashboardSchema(
            id=dashboard.id,
            title=dashboard.title,
            charts=json.loads(dashboard.charts),
            layout=json.loads(dashboard.layout),
            messages=json.loads(dashboard.messages),
            filters=json.loads(dashboard.filters) if dashboard.filters else [],
            images=json.loads(dashboard.images) if dashboard.images else [],
            presentation=json.loads(dashboard.presentation) if dashboard.presentation else None,
            dashboard_theme=dashboard.dashboard_theme or 'light',
            is_published=dashboard.is_published,
            share_id=dashboard.share_id,
            created_at=dashboard.created_at.isoformat() if dashboard.created_at else None,
            updated_at=dashboard.updated_at.isoformat() if dashboard.updated_at else None,
        )


async def delete_dashboard(dashboard_id: str) -> bool:
    """Delete a dashboard and its associated uploaded images."""
    async with get_db_session() as session:
        from sqlalchemy import select, delete
        result = await session.execute(
            select(DashboardModel).where(DashboardModel.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            return False

        # Delete associated uploaded images
        images = json.loads(dashboard.images) if dashboard.images else []
        for img in images:
            url = img.get('url', '')
            # Extract image ID from URL like /api/images/{image_id}
            if '/api/images/' in url:
                image_id = url.split('/api/images/')[-1]
                await session.execute(
                    delete(UploadedImageModel).where(UploadedImageModel.id == image_id)
                )

        await session.execute(
            delete(DashboardModel).where(DashboardModel.id == dashboard_id)
        )
        return True


async def publish_dashboard(dashboard_id: str) -> Optional[PublishResponseSchema]:
    """Publish a dashboard and generate a share ID."""
    import uuid

    async with get_db_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(DashboardModel).where(DashboardModel.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            return None

        # Generate share ID if not already published
        if not dashboard.share_id:
            dashboard.share_id = str(uuid.uuid4())[:8]

        dashboard.is_published = True
        dashboard.updated_at = datetime.utcnow()
        await session.flush()

        base_url = os.getenv("BASE_URL", "http://localhost:5175")

        return PublishResponseSchema(
            share_id=dashboard.share_id,
            share_url=f"{base_url}/shared/{dashboard.share_id}"
        )


async def unpublish_dashboard(dashboard_id: str) -> bool:
    """Unpublish a dashboard."""
    async with get_db_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(DashboardModel).where(DashboardModel.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            return False

        dashboard.is_published = False
        dashboard.updated_at = datetime.utcnow()
        await session.flush()
        return True


# Image CRUD operations

async def save_uploaded_image(image_id: str, filename: str, content_type: str, data: bytes) -> str:
    """Save an uploaded image to the database. Returns the image ID."""
    async with get_db_session() as session:
        image = UploadedImageModel(
            id=image_id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            data=data,
        )
        session.add(image)
        await session.flush()
        return image_id


async def get_uploaded_image(image_id: str) -> Optional[UploadedImageModel]:
    """Get an uploaded image by ID."""
    async with get_db_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(UploadedImageModel).where(UploadedImageModel.id == image_id)
        )
        return result.scalar_one_or_none()
