"""Published distribution guards shared by migrations and create_all.

These guards only add restrictions; mathematical Tier A/B guards stay installed.
"""
from dataclasses import dataclass


ENTITIES = ("symbol", "definition", "axiom", "axiom_system", "theorem", "proof")
DETAILS = {
    "symbol_alias": ("symbol", "symbol_id"),
    "definition_formal_param": ("definition", "definition_id"),
    "axiom_system_member": ("axiom_system", "axiom_system_id"),
    "theorem_premise": ("theorem", "theorem_id"),
    "theorem_tag": ("theorem", "theorem_id"),
    "axiom_tag": ("axiom", "axiom_id"),
    "definition_tag": ("definition", "definition_id"),
    "proof_identity_sequence": ("theorem", "theorem_id"),
    **{name: ("proof", "proof_id") for name in (
        "proof_step", "proof_step_arg", "proof_step_subst_term",
        "proof_step_subst_prop", "proof_step_subst_prop_param",
    )},
    "release_dependency": ("package_release", "release_id"),
    "release_lock_entry": ("package_release", "release_id"),
}


@dataclass(frozen=True)
class PublishedGuard:
    table: str
    event: str

    @property
    def name(self):
        return f"published_{self.table}_{self.event.lower()}"


PUBLISHED_GUARDS = tuple(
    PublishedGuard(table, event)
    for table in (*ENTITIES, *DETAILS, "package_release", "package", "tag", "formula")
    for event in (("UPDATE", "DELETE") if table in ("package_release", "package", "tag", "formula")
                  else ("INSERT", "UPDATE", "DELETE"))
    # Existing Tier A guards already reject every premise UPDATE and reject
    # DELETE while its theorem exists. The published theorem cannot be deleted.
    if not (table == "theorem_premise" and event in ("UPDATE", "DELETE"))
    # Tier B already forbids deleting every completed formula, published or not.
    if not (table == "formula" and event == "DELETE")
)


def _published(row, field="release_id"):
    return f"EXISTS (SELECT 1 FROM package_release r WHERE r.id = {row}.{field} AND r.published_at IS NOT NULL)"


def _parent(row, parent, field):
    if parent == "package_release":
        return _published(row, field)
    return (f"EXISTS (SELECT 1 FROM {parent} p JOIN package_release r ON r.id = p.release_id "
            f"WHERE p.id = {row}.{field} AND r.published_at IS NOT NULL)")


def guard_condition(guard, dialect):
    table, event = guard.table, guard.event
    rows = ("NEW",) if event == "INSERT" else ("OLD",) if event == "DELETE" else ("OLD", "NEW")
    if table in ENTITIES:
        terms = [_published(row) for row in rows]
        if table == "proof":
            terms += [_parent(row, "theorem", "theorem_id") for row in rows]
        return " OR ".join(terms)
    if table in DETAILS:
        return " OR ".join(_parent(row, *DETAILS[table]) for row in rows)
    if table == "package_release":
        if event == "DELETE":
            return "OLD.published_at IS NOT NULL"
        different = "IS NOT" if dialect == "sqlite" else "IS DISTINCT FROM"
        columns = ("id", "package_id", "version", "dem_runtime_range", "manifest", "content_digest", "published_at")
        # PostgreSQL JSON has no equality operator; compare its serialized value.
        def value(row, column):
            expr = f"{row}.{column}"
            return f"CAST({expr} AS TEXT)" if column == "manifest" and dialect == "postgresql" else expr
        return "OLD.published_at IS NOT NULL AND (" + " OR ".join(
            f"{value('NEW', col)} {different} {value('OLD', col)}" for col in columns
        ) + ")"
    if table == "package":
        return "EXISTS (SELECT 1 FROM package_release r WHERE r.package_id = OLD.id AND r.published_at IS NOT NULL)"
    if table == "tag":
        return " OR ".join(
            f"EXISTS (SELECT 1 FROM {kind}_tag t JOIN {kind} p ON p.id = t.{kind}_id "
            "JOIN package_release r ON r.id = p.release_id "
            "WHERE t.tag_id = OLD.id AND r.published_at IS NOT NULL)"
            for kind in ("theorem", "axiom", "definition")
        )
    if table == "formula":
        # All direct formula references, including substitutions, use the same
        # ForeignKeyConstraint column pairing as dependency closure.
        from dem.services.package import _references
        from sqlalchemy import select
        from sqlalchemy.dialects import postgresql, sqlite
        sql_dialect = sqlite.dialect() if dialect == "sqlite" else postgresql.dialect()
        terms = []
        if dialect == "sqlite":
            archived = "SELECT value FROM json_each(r.manifest, '$._archive_formula_ids')"
        else:
            archived = "SELECT json_array_elements_text(r.manifest->'_archive_formula_ids')"
        terms.append("EXISTS (SELECT 1 FROM package_release r WHERE r.published_at IS NOT NULL "
                     f"AND OLD.public_id IN ({archived}))")
        for _, constraint, owner, source, target in _references():
            if target.name != "formula":
                continue
            query = select(owner.c.release_id).select_from(source)
            pairs = " AND ".join(f"{fk.parent.table.name}.{fk.parent.name} = OLD.{fk.column.name}"
                                 for fk in constraint.elements)
            compiled = str(query.compile(dialect=sql_dialect))
            terms.append(f"EXISTS (SELECT 1 FROM package_release r WHERE r.published_at IS NOT NULL "
                         f"AND r.id IN ({compiled} WHERE {pairs}))")
        return " OR ".join(terms)
    raise AssertionError(table)


def create_published_triggers(connection):
    dialect = connection.dialect.name
    for guard in PUBLISHED_GUARDS:
        condition = guard_condition(guard, dialect)
        if dialect == "sqlite":
            connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS {guard.name}
                BEFORE {guard.event} ON {guard.table} FOR EACH ROW WHEN {condition}
                BEGIN SELECT RAISE(ABORT, 'published release is immutable: {guard.name}'); END""")
        elif dialect == "postgresql":
            returned = "OLD" if guard.event == "DELETE" else "NEW"
            connection.exec_driver_sql(f"""CREATE OR REPLACE FUNCTION {guard.name}() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                IF {condition} THEN RAISE EXCEPTION 'published release is immutable: {guard.name}' USING ERRCODE = '23514'; END IF;
                RETURN {returned}; END $$""")
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {guard.name} ON {guard.table}")
            connection.exec_driver_sql(f"CREATE TRIGGER {guard.name} BEFORE {guard.event} ON {guard.table} "
                                       f"FOR EACH ROW EXECUTE FUNCTION {guard.name}()")
        else:
            raise RuntimeError(f"unsupported published-release dialect: {dialect}")


def drop_published_triggers(connection):
    for guard in reversed(PUBLISHED_GUARDS):
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {guard.name}")
        else:
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {guard.name} ON {guard.table}")
            connection.exec_driver_sql(f"DROP FUNCTION IF EXISTS {guard.name}()")
