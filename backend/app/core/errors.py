"""Consistent JSON error responses.

Every error returned to a client has the shape::

    {"error": {"code": "FILE_NOT_FOUND", "message": "..."}}

Internal details (tracebacks, file paths, library messages) are only logged,
never returned.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

logger = logging.getLogger(__name__)


class AppError(Exception):
    """An error that is safe to show to the client."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _error_response(
    status_code: int, code: str, message: str, details: list | None = None
) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers so that every failure produces the same JSON shape."""

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return _error_response(422, "VALIDATION_ERROR", "The request is invalid.", details)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return _error_response(exc.status_code, code, str(exc.detail))

    @app.middleware("http")
    async def handle_unexpected_error(request: Request, call_next) -> Response:
        """Turn any unhandled exception into a generic JSON 500.

        This is a middleware (not an ``Exception`` handler) so that it runs *inside* the CORS
        middleware: the browser can then read the 500 response instead of reporting a network error.
        """
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")
