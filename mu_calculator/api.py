"""Public read-only MU API."""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from . import Grump, MODEL
from .coordinates import calculate

BODY_LIMIT = int(os.environ.get("MU_BODY_LIMIT", 32768))
BULK_LIMIT = int(os.environ.get("MU_BULK_LIMIT", 50))
TIME_BUDGET = float(os.environ.get("MU_TIME_BUDGET", 20))
SELF_TEST = ["52.324297,10.182664", "52.244048,10.167482", "52.295984,10.231064"]
# Serialize calculations: one bounded worker owns the density cache.
executor = ThreadPoolExecutor(max_workers=1)


@asynccontextmanager
async def lifespan(app):
    app.state.grump = Grump()
    if not app.state.grump.r or calculate(app.state.grump, SELF_TEST)["mu"] != 3046:
        raise RuntimeError(
            "Population data startup self-test failed (expected 3046 MU)."
        )
    yield


app = FastAPI(title="MU Calculator", lifespan=lifespan)


class BodyTooLarge(Exception):
    pass


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > BODY_LIMIT:
                raise BodyTooLarge()
            return message

        await self.app(scope, limited_receive, send)


app.add_middleware(BodyLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def error(message, status=400, **kwargs):
    return JSONResponse(
        {"error": message, "model": MODEL}, status_code=status, **kwargs
    )


@app.exception_handler(HTTPException)
async def http_error(request, exception):
    return error(str(exception.detail), exception.status_code)


@app.exception_handler(BodyTooLarge)
async def too_large(request, exception):
    return error("Request body exceeds limit.", 413)


@app.exception_handler(Exception)
async def unexpected(request, exception):
    logging.exception("Request failed", exc_info=exception)
    # This handler runs outside the CORS middleware, so add the header here.
    return error("Calculation failed.", 500, headers={"Access-Control-Allow-Origin": "*"})


def reject_constant(name):
    raise ValueError(name)


async def payload(request):
    try:
        value = json.loads(await request.body(), parse_constant=reject_constant)
    except (ValueError, RecursionError):
        raise ValueError("Malformed JSON.") from None
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def detail_flag(value):
    if value in (False, None, "0", 0):
        return False
    if value in (True, "1", 1):
        return True
    raise ValueError("detail must be true, false, 1 or 0.")


def result(grump, coordinates, detail):
    response = calculate(grump, coordinates)
    if not detail:
        response = {key: response[key] for key in ("mu", "area_km2", "coordinates")}
    return dict(response, model=MODEL)


async def within_deadline(function, deadline):
    def guarded():
        if time.monotonic() >= deadline:
            raise TimeoutError()
        return function()

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError()
    return await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(executor, guarded), remaining
    )


@app.get("/")
def root():
    return {
        "description": "Independent empirical Ingress MU calculator.",
        "docs": "https://mu.investigatexm.com",
        "api_docs": "/docs",
        "model": MODEL,
    }


@app.get("/health")
def health():
    return {"ok": True, "rasters": len(app.state.grump.r), "model": MODEL}


@app.api_route("/getMU", methods=["GET", "POST"])
async def get_mu(request: Request):
    deadline = time.monotonic() + TIME_BUDGET
    try:
        body = (
            await payload(request)
            if request.method == "POST"
            else {"coordinates": request.query_params.getlist("c")}
        )
        detail = detail_flag(
            request.query_params.get("detail", body.get("detail", False))
        )
        return await within_deadline(
            lambda: result(app.state.grump, body.get("coordinates"), detail), deadline
        )
    except ValueError as exception:
        return error(str(exception))
    except TimeoutError:
        return error("deadline exceeded", 504)


@app.post("/getMUbulk")
async def get_bulk(request: Request):
    deadline = time.monotonic() + TIME_BUDGET
    try:
        body = await payload(request)
        fields = body.get("fields")
        if not isinstance(fields, list) or not 1 <= len(fields) <= BULK_LIMIT:
            raise ValueError(f"fields must be an array of 1 to {BULK_LIMIT} triangles.")
        detail = detail_flag(
            request.query_params.get("detail", body.get("detail", False))
        )
    except ValueError as exception:
        return error(str(exception))
    results = []
    for index, field in enumerate(fields):
        item = {"index": index}
        if isinstance(field, dict) and "id" in field:
            item["id"] = field["id"]
        coordinates = field.get("coordinates") if isinstance(field, dict) else field
        try:
            calculated = await within_deadline(
                lambda: result(app.state.grump, coordinates, detail), deadline
            )
            calculated.pop("model")
            item.update(ok=True, **calculated)
        except ValueError as exception:
            item.update(ok=False, error=str(exception))
        except TimeoutError:
            item.update(ok=False, error="deadline exceeded")
        results.append(item)
    return {"count": len(results), "results": results, "model": MODEL}
