from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dem.errors import DemError, ConflictError, NotFoundError, ProofValidationError, ValidationError

from dem.types import Token


def _error_context(exc: DemError) -> dict:
    body = {}
    if exc.code is not None:
        body["code"] = exc.code
    if exc.details:
        body["details"] = {
            key: {"tokens": [
                {"position": i, "symbol_id": token.symbol_id,
                 "de_bruijn_index": token.de_bruijn_index}
                for i, token in enumerate(value)
            ]} if key in {"expected", "actual"} and isinstance(value, (list, tuple))
            and all(isinstance(token, Token) for token in value) else value
            for key, value in exc.details.items()
        }
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={**_error_context(exc), "detail": str(exc), "entity": exc.entity, "id": str(exc.id)},
        )

    @app.exception_handler(ProofValidationError)
    async def _proof_validation(request: Request, exc: ProofValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={**_error_context(exc), "detail": str(exc), "step_ord": exc.step_ord},
        )

    @app.exception_handler(ValidationError)
    async def _validation(request: Request, exc: ValidationError) -> JSONResponse:
        position = getattr(exc, "position", None)
        return JSONResponse(status_code=422, content={**_error_context(exc), "detail": str(exc), "position": position})

    @app.exception_handler(ConflictError)
    async def _conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={**_error_context(exc), "detail": str(exc), "entity": exc.entity, "field": exc.field, "value": exc.value},
        )
