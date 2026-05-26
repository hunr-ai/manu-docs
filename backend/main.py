import os
from contextlib import asynccontextmanager

from auth.router import router as auth_router
from config.settings.schemas import DatabaseSettings, RedisSettings
from config.settings.settings_loader import get_settings_loader
from deps.redis_dep import RedisClient
from emails.router import router as emails_router
from fastapi import FastAPI
from observability.logging import configure_logging
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from structlog import get_logger
from temporalio.client import Client

environment = os.environ.setdefault("ENVIRONMENT", "dev")
configure_logging(service_name="manudocs-api", environment=environment)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Add settings to app state
    await logger.ainfo("Application startup started", environment=environment)
    settings_loader = get_settings_loader(environment)
    settings = await settings_loader.load_settings()
    app.state.settings_loader = settings_loader
    app.state.settings = settings

    # Add database engine and session factory to app state
    await logger.ainfo("Settings loaded", settings_count=len(settings))
    db_settings = settings_loader.get_required_settings(settings, DatabaseSettings)
    db_engine = create_async_engine(
        db_settings.url.get_secret_value(),
        pool_size=db_settings.pool_size,
        max_overflow=db_settings.max_overflow,
        pool_pre_ping=True,
    )
    app.state.db_engine = db_engine
    app.state.db_sessionmaker = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    # Add redis client to app state
    await logger.ainfo("Database engine initialized")
    redis_settings = settings_loader.get_required_settings(settings, RedisSettings)
    redis_client = RedisClient(redis_settings).client
    app.state.redis_client = redis_client
    await logger.ainfo("Redis client initialized")

    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    app.state.temporal_client = await Client.connect(
        temporal_address,
        namespace=temporal_namespace,
    )
    await logger.ainfo(
        "Temporal client connected",
        temporal_address=temporal_address,
        temporal_namespace=temporal_namespace,
    )

    try:
        await logger.ainfo("Application startup completed")
        yield
    finally:
        await logger.ainfo("Application shutdown started")
        await db_engine.dispose()
        await redis_client.aclose()
        await logger.ainfo("Application shutdown completed")


app = FastAPI(lifespan=lifespan)
app.include_router(emails_router)
app.include_router(auth_router)
