from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeoutError

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
    from webapi.beta import BetaReject, reject_response
    from webapi.db_guards import known_guard

    @app.exception_handler(RecursionError)
    async def _formula_too_deep(request: Request, exc: RecursionError) -> JSONResponse:
        return JSONResponse(status_code=422, content={
            "detail": "Formula processing exceeded the supported recursion depth",
            "code": "formula.too_deep",
        })

    @app.exception_handler(BetaReject)
    async def _beta_rejected(request: Request, exc: BetaReject) -> JSONResponse:
        return reject_response(exc, getattr(request.state, "beta_route", "<unmatched>"),
                               getattr(request.state, "beta_category", "write"))

    @app.exception_handler(DBAPIError)
    async def _db_guard(request: Request, exc: DBAPIError) -> JSONResponse:
        guard = known_guard(exc)
        if guard is None:
            raise exc
        return JSONResponse(status_code=409, content={
            "detail": "Database guard rejected the operation", "code": "db.guard_rejected",
        })

    @app.exception_handler(PoolTimeoutError)
    async def _pool_busy(request: Request, exc: PoolTimeoutError) -> JSONResponse:
        from webapi.beta import enabled
        # SQLAlchemy QueuePool._do_get raises 3o7r before returning a connection.
        # Do not disguise other timeout errors or change the non-beta response.
        if not enabled() or exc.code != "3o7r":
            raise exc
        return reject_response(BetaReject(503, "beta.database_busy", "Database connections are busy", 2),
                               getattr(request.state, "beta_route", "<unmatched>"),
                               getattr(request.state, "beta_category", "read"))

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
