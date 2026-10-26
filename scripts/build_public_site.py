"""Build crawlable DEM Public HTML from a read-only database snapshot."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import cache
from html import escape
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from time import perf_counter
from urllib.parse import urlsplit
from uuid import UUID
from xml.etree import ElementTree as ET

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from dem.db.models.definition import Definition
from dem.db.models.inference import Axiom, AxiomSystem, AxiomSystemMember
from dem.db.models.language import Symbol
from dem.db.models.theorem import Proof, ProofStep, Theorem, TheoremPremise
from dem.services.formula import FormulaService
from dem.services.system_tags import visible_theorem_clause
from dem.types import Token

SITE_NAME = "Deus Ex Machina"
FIXED = (
    ("/", "", "定理・公理・定義・記号と形式的な証明を閲覧できます。"),
    ("/theorems", "定理", "定理の主張と証明を閲覧できます。"),
    ("/axioms", "公理", "公理と公理系を閲覧できます。"),
    ("/definitions", "定義", "記号の定義と定義の式を閲覧できます。"),
    ("/symbols", "記号", "形式的な式で使う記号と注記を閲覧できます。"),
    ("/proofs", "証明", "定理の証明と検証状態を閲覧できます。"),
    ("/search", "定理を探す", "主張や条件から定理を探せます。"),
    ("/terms", "利用規約", "Deus Ex Machina の利用規約です。"),
    ("/privacy", "プライバシーポリシー", "Deus Ex Machina のプライバシーポリシーです。"),
    ("/disclaimer", "免責事項", "Deus Ex Machina の免責事項です。"),
    ("/sources-licenses", "出典とライセンス", "収録内容の出典とライセンスについて。"),
)


@contextmanager
def readonly_session(database_url: str):
    """Enforce read-only access in the database, not merely by convention."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if not url.database or url.database == ":memory:" or url.query:
            raise ValueError("Use a SQLite file URL without query parameters")
        uri = Path(url.database).resolve().as_uri() + "?mode=ro"
        engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False))
    elif url.get_backend_name() == "postgresql":
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        engine = create_engine(url, isolation_level="REPEATABLE READ")
    else:
        raise ValueError("Only SQLite and PostgreSQL are supported")
    try:
        with engine.connect() as connection:
            with connection.begin():
                if engine.dialect.name == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                else:
                    # Explicit BEGIN also makes SQLite reads a consistent snapshot.
                    connection.exec_driver_sql("BEGIN")
                with Session(bind=connection, autoflush=False) as session:
                    yield session
                connection.rollback()
    finally:
        engine.dispose()


def public_path(kind: str, public_id: str) -> str:
    # Public IDs are UUIDs; fail closed rather than turning DB text into file paths.
    if str(UUID(public_id)) != public_id:
        raise ValueError("Noncanonical public ID")
    return f"/{kind}/{public_id}"


def normalize_base_url(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme not in ("http", "https") or not url.hostname
            or url.username or url.password or url.query or url.fragment
            or url.path not in ("", "/") or any(c.isspace() for c in value)):
        raise ValueError("--base-url must be an HTTP(S) origin (no path, credentials, query or fragment)")
    return value.rstrip("/")


def description(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 160 else text[:159] + "…"


@dataclass
class Page:
    path: str
    name: str
    text: str
    kind: str
    links: list[tuple[str, str]] = field(default_factory=list)

    @property
    def title(self) -> str:
        return f"{self.name} — {SITE_NAME}" if self.name else SITE_NAME


def collect_pages(session: Session) -> list[Page]:
    pages = {path: Page(path, name, text, "fixed") for path, name, text in FIXED}
    formulas = FormulaService(session)

    @cache
    def formula_text(formula_id: int) -> str:
        return formulas.print_text([Token(symbol_id=t.symbol_id, de_bruijn_index=t.de_bruijn_index)
                                    for t in formulas.get_tokens(formula_id)])

    def rows(model):
        return session.execute(select(model.__table__)).mappings().all()

    def add(page: Page, listing: str):
        if page.path in pages:
            raise ValueError(f"Duplicate page: {page.path}")
        pages[page.path] = page
        pages[listing].links.append((page.path, page.name))
        page.links.append((listing, pages[listing].name))

    symbols = {s.id: s for s in rows(Symbol)}
    axioms = {a.id: a for a in rows(Axiom)}
    definition_axioms = {a.definition_id: a for a in axioms.values() if a.definition_id is not None}
    for s in symbols.values():
        add(Page(public_path("symbols", s.public_id), s.name,
                 s.remarks or f"記号「{s.name}」。", "symbols"), "/symbols")
    for a in axioms.values():
        add(Page(public_path("axioms", a.public_id), a.name,
                 formula_text(a.formula_id), "axioms"), "/axioms")
    for d in rows(Definition):
        axiom = definition_axioms[d.id]
        page = Page(public_path("definitions", d.public_id), d.name,
                    formula_text(d.display_formula_id or axiom.formula_id), "definitions")
        page.links.extend([(public_path("axioms", axiom.public_id), axiom.name),
                           (public_path("symbols", symbols[d.new_symbol_id].public_id), d.name)])
        add(page, "/definitions")
        pages[public_path("symbols", symbols[d.new_symbol_id].public_id)].links.append((page.path, page.name))
    members: dict[int, list[int]] = {}
    for m in rows(AxiomSystemMember):
        members.setdefault(m.axiom_system_id, []).append(m.axiom_id)
    for s in rows(AxiomSystem):
        ids = members.get(s.id, [])
        page = Page(public_path("axiom-systems", s.public_id), s.name,
                    f"{s.name}。公理 {len(ids)} 個。", "axiom-systems")
        page.links.extend((public_path("axioms", axioms[i].public_id), axioms[i].name) for i in ids)
        add(page, "/axioms")

    theorems = {t.id: t for t in session.execute(
        select(Theorem.__table__).where(visible_theorem_clause(Theorem.id))
    ).mappings()}
    premises: dict[int, list[str]] = {}
    for p in session.execute(select(TheoremPremise.__table__).order_by(TheoremPremise.ord)).mappings():
        if p.theorem_id in theorems:
            premises.setdefault(p.theorem_id, []).append(formula_text(p.formula_id))
    for t in theorems.values():
        status = {"proven": "証明済み", "conjecture": "予想"}[t.status]
        statement = formula_text(t.conclusion_formula_id)
        if premises.get(t.id):
            statement = "前提: " + "、".join(premises[t.id]) + "。結論: " + statement
        add(Page(public_path("theorems", t.public_id), t.name,
                 f"{status}。{statement}", "theorems"), "/theorems")
    counts = dict(session.execute(select(ProofStep.proof_id, func.count())
                                 .group_by(ProofStep.proof_id)).all())
    for p in session.execute(select(Proof.__table__).join(Theorem, Theorem.id == Proof.theorem_id)
                             .where(visible_theorem_clause(Theorem.id))).mappings():
        t = theorems[p.theorem_id]
        parent = public_path("theorems", t.public_id)
        path = parent + public_path("proofs", p.public_id)
        status = {"verified": "検証済み", "draft": "下書き", "rejected": "却下"}[p.status]
        page = Page(path, t.name + "の証明",
                    f"{t.name}の証明。{counts.get(p.id, 0)} ステップ。{status}。", "proofs",
                    [(parent, t.name)])
        add(page, "/proofs")
        pages[parent].links.append((path, page.name))
    pages["/"].links.extend((path, name) for path, name, _ in FIXED if path != "/")
    pages["/search"].links.append(("/theorems", "定理"))
    for page in pages.values():
        page.links = sorted(set(page.links))
    return sorted(pages.values(), key=lambda p: p.path)


def render_page(template: str, page: Page, base_url: str) -> str:
    canonical = base_url + page.path
    desc = description(page.text)
    meta = "\n".join([
        f'<title>{escape(page.title)}</title>',
        f'<meta name="description" content="{escape(desc)}">',
        f'<link rel="canonical" href="{escape(canonical)}">',
        *[f'<meta property="og:{key}" content="{escape(value)}">' for key, value in (
            ("title", page.title), ("description", desc), ("url", canonical),
            ("type", "website"), ("site_name", SITE_NAME), ("locale", "ja_JP"))],
        '<meta name="twitter:card" content="summary">',
    ])
    body = (f'<main data-public-static="true"><h1>{escape(page.name or SITE_NAME)}</h1>'
            f'<p>{escape(page.text)}</p><nav><ul>'
            + "".join(f'<li><a href="{escape(path)}">{escape(name)}</a></li>'
                      for path, name in page.links) + '</ul></nav></main>')
    html, title_count = re.subn(r"<title>.*?</title>", lambda _: meta, template, flags=re.DOTALL)
    html, root_count = re.subn(r'<div id="root">\s*</div>',
                              lambda _: f'<div id="root">{body}</div>', html)
    if title_count != 1 or root_count != 1:
        raise ValueError('Expected one <title> and one empty <div id="root"> in the Vite build')
    return html


def build_site(database_url: str, frontend: Path, base_url: str, output: Path,
               *, proof_ids: set[str] | None = None) -> dict:
    from scripts.public_api_data import capture_data, public_api, write_data
    started = perf_counter()
    base_url = normalize_base_url(base_url)
    frontend, output = frontend.resolve(), output.resolve()
    if output.exists() or frontend == output or frontend in output.parents or output in frontend.parents:
        raise ValueError("Output must be a new directory outside the frontend build")
    template = (frontend / "index.html").read_text(encoding="utf-8")
    if not (frontend / "assets").is_dir():
        raise ValueError("Expected a production frontend build with assets/")
    with readonly_session(database_url) as session:
        pages = collect_pages(session)
        data_started = perf_counter()
        with public_api(session) as application:
            data = asyncio.run(capture_data(session, application, proof_ids))
        data_elapsed = perf_counter() - data_started
    # Render first so malformed inputs cannot produce a partially usable release.
    fonts = sorted(path for family in ("Main-Regular", "Math-Italic", "SansSerif-Regular")
                   for path in (frontend / "assets").glob(f"KaTeX_{family}-*.woff2"))
    preload = "".join(f'<link rel="preload" href="/assets/{escape(p.name)}" as="font" '
                      'type="font/woff2" crossorigin="anonymous">' for p in fonts)
    rendered = [(p, render_page(template.replace('</head>', preload + '</head>')
                               if p.kind == "proofs" else template, p, base_url)) for p in pages]
    shutil.copytree(frontend, output)
    data_summary = write_data(output, data)
    for page, html in rendered:
        html = html.replace('</head>', '<meta name="dem-public-data" content="'
                            + escape(data_summary["data_path"]) + '"></head>')
        target = output / page.path.lstrip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(html.encode("utf-8"))
    sitemap = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for page in pages:
        ET.SubElement(ET.SubElement(sitemap, "url"), "loc").text = base_url + page.path
    ET.ElementTree(sitemap).write(output / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    (output / "robots.txt").write_bytes(
        f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n".encode("utf-8"))
    return {**data_summary, "data_elapsed_seconds": round(data_elapsed, 3),
            "pages_by_kind": dict(sorted(Counter(p.kind for p in pages).items())),
            "sitemap_urls": len(pages),
            "output_bytes": sum(p.stat().st_size for p in output.rglob("*") if p.is_file()),
            "elapsed_seconds": round(perf_counter() - started, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--frontend", required=True, type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--proof-id", action="append", help="Limit data to these public proof IDs (measurement only)")
    args = parser.parse_args()
    result = build_site(args.database_url, args.frontend, args.base_url, args.output,
                        proof_ids=set(args.proof_id) if args.proof_id else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
