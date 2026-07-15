from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.errors import (
    ApplicationError,
    DomainConflict,
    ResourceNotFound,
    ValidationFailure,
)
from app.core.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Spectrum Ledger API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get(
            "x-request-id", str(uuid.uuid4())
        )
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        request: Request, exc: ApplicationError
    ) -> JSONResponse:
        if isinstance(exc, ResourceNotFound):
            status_code = 404
        elif isinstance(exc, DomainConflict):
            status_code = 409
        elif isinstance(exc, ValidationFailure):
            status_code = 422
        else:
            status_code = 400
        return _error_response(request, exc, status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        error = ValidationFailure(
            "INVALID_REQUEST", "request validation failed", details={"errors": exc.errors()}
        )
        return _error_response(request, error, 422)

    app.include_router(router)
    return app


def _error_response(
    request: Request, exc: ApplicationError, status_code: int
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request.state.request_id,
                "details": exc.details,
            }
        },
    )


app = create_app()
