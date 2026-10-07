import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.certificates import router as certificates_router
from app.core.config import settings
from app.db.database import init_db

# Configure application logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bulk_certificate_generator")


# Ensure database tables exist immediately upon import
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown routines."""
    logger.info("Initializing database schema...")
    init_db()
    # Ensure generated certificates directory exists
    _ = settings.certificates_dir_path
    logger.info("Application startup complete. Ready to receive requests.")
    yield
    logger.info("Application shutdown.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-quality REST API for asynchronous, fault-tolerant "
        "bulk certificate generation with progress tracking."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected server errors without exposing internal stack traces."""
    logger.critical(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact the administrator."},
    )


@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
    description="Check whether the API service is alive and healthy.",
)
def health_check() -> dict:
    """Simple health check endpoint returning service status."""
    return {"status": "healthy"}


# Register API routers
app.include_router(certificates_router, prefix="/api/v1")
