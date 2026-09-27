"""Phase 2.5 structural formula search contracts."""

from __future__ import annotations

import asyncio
import json
from statistics import median
from time import perf_counter

import pytest
from sqlalchemy import func, select

from dem.api import DemServices
from dem.db.models.language import Formula, FormulaToken
from dem.types import SymbolTypeName, Token
from demlang.match import match_formula
from webapi.deps import dem_services
from webapi.main import app
from webapi.schemas import FormulaSearchOut


@pytest.fixture
def api(all_seeded_session):
    dem = DemServices(all_seeded_session)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[dem_services] = lambda: dem

    def post(body):
        async def request():
            payload = json.dumps(body).encode()
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/formulas/search",
                "raw_path": b"/formulas/search",
                "root_path": "",
                "query_string": b"",
                "headers": [
                    (b"host", b"test"),
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
                "server": ("test", 80),
                "client": ("test", 1234),
            }
            messages = []
            sent = False

            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": payload, "more_body": False}
                await asyncio.Event().wait()

            async def send(message):
                messages.append(message)

            await asyncio.wait_for(app(scope, receive, send), timeout=30)
            start = next(item for item in messages if item["type"] == "http.response.start")
            response_body = b"".join(
                item.get("body", b"")
                for item in messages
                if item["type"] == "http.response.body"
            )
            return start["status"], json.loads(response_body)

        return asyncio.run(request())

    try:
        yield dem, post
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.fixture(scope="module")
def formula_corpus(all_seeded_session):
    dem = DemServices(all_seeded_session)
    rows = dem.session.execute(
        select(
            FormulaToken.formula_id,
            FormulaToken.symbol_id,
            FormulaToken.de_bruijn_index,
        ).order_by(FormulaToken.formula_id, FormulaToken.position)
    )
    tokens_by_formula: dict[int, list[Token]] = {}
    for formula_id, symbol_id, de_bruijn_index in rows:
        tokens_by_formula.setdefault(formula_id, []).append(
            Token(symbol_id=symbol_id, de_bruijn_index=de_bruijn_index)
        )
    meta = {
        symbol.id: symbol.meta
        for symbol in dem.formulas.surface_symbol_table().symbols.values()
    }
    return dem, tokens_by_formula, meta


@pytest.mark.parametrize(
    "pattern_text",
    [
        "φ → ψ ∧ φ",  # fixed root
        "φ",  # no fixed symbol
        "φ¹(x)",  # arity-bearing schema root without a fixed symbol
    ],
)
def test_structural_prefilter_preserves_full_scan_matches(
    formula_corpus, pattern_text,
):
    dem, tokens_by_formula, meta = formula_corpus
    pattern, _ = dem.formulas.parse_text(pattern_text)
    full_scan = {
        formula_id
        for formula_id, tokens in tokens_by_formula.items()
        if match_formula(pattern, tokens, meta) is not None
    }
    filtered = {
        formula_id
        for formula_id, _ in dem.formulas.search(pattern, limit=40_000)
    }
    assert filtered == full_scan


def test_structural_search_worst_case_measurement(api, capsys):
    dem, post = api
    pattern, _ = dem.formulas.parse_text("φ")
    formula_count = dem.session.scalar(select(func.count()).select_from(Formula))

    started = perf_counter()
    matches = dem.formulas.search(pattern, limit=formula_count)
    exhaustive_elapsed = perf_counter() - started
    started = perf_counter()
    status, body = post({"pattern": "φ", "context": {}, "limit": 500})
    max_page_elapsed = perf_counter() - started

    with capsys.disabled():
        print(
            "\n/formulas/search fixed-free exhaustive time: "
            f"{exhaustive_elapsed:.3f}s; max-page response time: "
            f"{max_page_elapsed:.3f}s"
        )
    assert len(matches) == formula_count
    assert status == 200
    assert len(body["items"]) == formula_count


@pytest.mark.timing_sensitive
def test_structural_search_schema_root_arity_measurement(api, capsys):
    dem, post = api
    pattern, _ = dem.formulas.parse_text("φ¹(x)")
    formula_count = dem.session.scalar(select(func.count()).select_from(Formula))

    started = perf_counter()
    matches = dem.formulas.search(pattern, limit=formula_count)
    exhaustive_elapsed = perf_counter() - started
    page_samples = []
    for _ in range(3):
        started = perf_counter()
        status, body = post({"pattern": "φ¹(x)", "context": {}, "limit": 500})
        page_samples.append(perf_counter() - started)
    max_page_elapsed = median(page_samples)

    with capsys.disabled():
        print(
            "\n/formulas/search schema-root arity exhaustive time: "
            f"{exhaustive_elapsed:.3f}s ({len(matches)} matches); "
            f"max-page response median: {max_page_elapsed:.3f}s "
            f"(samples: {', '.join(f'{sample:.3f}s' for sample in page_samples)})"
        )
    assert status == 200
    assert len(body["items"]) == min(500, len(matches))
    assert max_page_elapsed < 0.5


@pytest.mark.timing_sensitive
def test_structural_search_response_time_and_pagination(api, capsys):
    dem, post = api
    assert dem.session.scalar(select(func.count()).select_from(Formula)) == 8
    request = {"pattern": "φ → ψ", "context": {}, "limit": 50}
    assert post(request)[0] == 200  # warm SQLite pages and service caches
    samples = []
    for _ in range(3):
        started = perf_counter()
        status, body = post(request)
        samples.append(perf_counter() - started)
    elapsed = median(samples)
    with capsys.disabled():
        print(
            f"\n/formulas/search response median: {elapsed:.3f}s "
            f"(samples: {', '.join(f'{sample:.3f}s' for sample in samples)})"
        )
    assert status == 200
    assert set(body) == set(FormulaSearchOut.model_fields)
    assert body["items"]
    assert elapsed < 0.5

    if body["next_cursor"] is not None:
        next_status, next_body = post({**request, "cursor": body["next_cursor"]})
        assert next_status == 200
        assert {
            item["formula_id"] for item in body["items"]
        }.isdisjoint(item["formula_id"] for item in next_body["items"])


def test_structural_search_reports_formula_syntax_error(api):
    _, post = api
    status, body = post({"pattern": "(unknown", "limit": 50})
    assert status == 422
    assert body["code"] == "formula.syntax_error"


def test_structural_search_rejects_ambiguous_short_symbol(api):
    dem, post = api
    prop_type = dem.symbols.get_symbol_type_by_name(
        SymbolTypeName.FREE_PROP_VAR.value
    )
    dem.symbols.register(
        "search_collision", prop_type.id, 0, namespace="local.search-alpha"
    )
    dem.symbols.register(
        "search_collision", prop_type.id, 0, namespace="local.search-beta"
    )
    status, body = post({"pattern": "search_collision", "limit": 50})
    assert status == 422
    assert body["code"] == "formula.ambiguous_symbol"
