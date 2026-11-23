import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from incident_atlas import __version__
from incident_atlas.config import get_settings
from incident_atlas.db import SessionLocal
from incident_atlas.errors import ApiError
from incident_atlas.observability import configure_otel
from incident_atlas.routes import liveness, readiness, router

logger = logging.getLogger("incident_atlas.api")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_otel(app, settings)
    yield


app = FastAPI(
    title="Incident Atlas API",
    description="Bounded investigation API over deterministic synthetic incident evidence.",
    version=__version__,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-Incident-Atlas-Visitor-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
app.include_router(router)


def _problem(
    request: Request,
    status: int,
    code: str,
    detail: str,
    retryable: bool = False,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        headers=response_headers,
        content={
            "type": "about:blank",
            "title": code.replace("_", " ").title(),
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": getattr(request.state, "request_id", ""),
            "retryable": retryable,
        },
    )


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    headers = {"Retry-After": "60"} if exc.retryable and exc.status in {429, 503, 504} else None
    return _problem(request, exc.status, exc.code, exc.detail, exc.retryable, headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _problem(request, 422, "validation_error", "The request did not match the API contract.")


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "http_error"
    detail = (
        "The requested route does not exist."
        if exc.status_code == 404
        else "The request could not be completed."
    )
    return _problem(request, exc.status_code, code, detail, headers=exc.headers)


@app.exception_handler(Exception)
async def unknown_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "request_failed request_id=%s exception_type=%s",
        getattr(request.state, "request_id", ""),
        type(exc).__name__,
    )
    return _problem(request, 500, "internal_error", "The server could not complete the request.")


@app.middleware("http")
async def request_context_and_limits(request: Request, call_next):
    request_id = f"req_{uuid.uuid4().hex}"
    request.state.request_id = request_id
    if request.method in {"POST", "PUT", "PATCH"} and request.url.path.startswith("/api/v1/"):
        content_length = request.headers.get("content-length")
        if content_length is None:
            return _problem(
                request,
                411,
                "content_length_required",
                "This endpoint requires a bounded Content-Length.",
            )
        try:
            body_size = int(content_length)
        except ValueError:
            return _problem(
                request, 400, "invalid_content_length", "Content-Length must be an integer."
            )
        if body_size < 0 or body_size > settings.max_request_bytes:
            limit_kib = settings.max_request_bytes // 1024
            return _problem(
                request,
                413,
                "request_too_large",
                f"Request body exceeds the configured {limit_kib} KiB limit.",
            )

    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%d",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        int((time.monotonic() - started) * 1000),
    )
    return response


@app.get("/healthz", include_in_schema=False)
def healthz():
    return liveness()


@app.get("/readyz", include_in_schema=False)
def readyz(request: Request):
    with SessionLocal() as db:
        return readiness(db, request)
