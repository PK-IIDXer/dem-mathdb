"""Public identity guards without the expensive logical seed cascade."""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models import Base
from dem.db.seed import seed_language
from dem.types import LogicalDefinitionInput, SymbolTypeName, Token
from test_alembic_history import _empty_database_pair, _migrate

ENTITIES = ('axiom_system', 'axiom', 'definition', 'theorem', 'proof', 'formula', 'symbol')
ADDED = ENTITIES[:5]


def create_rows(session):
    seed_language(session)
    dem = DemServices(session)
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    symbol = dem.symbols.register('identity-variable', kind.id, 0, namespace='test.identity')
    formula = dem.formulas.register([Token(symbol_id=symbol.id)])
    axiom = dem.axioms.register('identity-axiom', formula.id, namespace='test.identity')
    definition = dem.definitions.register(LogicalDefinitionInput(
        name='identity-definition', param_symbol_ids=(symbol.id,), body_formula_id=formula.id,
    ), namespace='test.identity')
    theorem = dem.theorems.register('identity-theorem', formula.id, namespace='test.identity')
    proof = dem.proofs.create_proof(theorem.id)
    system = dem.axioms.register_system('identity-system', namespace='test.identity')
    dem.axioms.add_to_system(system.id, axiom.id)
    session.flush()
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    return dict(zip(ENTITIES, (system, axiom, definition, theorem, proof, formula, symbol)))


@pytest.fixture(scope='module', params=['model', 'migration'])
def identity_engine(request, tmp_path_factory):
    with _empty_database_pair(tmp_path_factory.mktemp('public-identity-' + request.param)) as (migration, model):
        engine = model if request.param == 'model' else migration
        if request.param == 'model':
            Base.metadata.create_all(engine)
        else:
            _migrate(engine.url, 'head')
        yield engine


@pytest.fixture
def identity_rows(identity_engine):
    with Session(identity_engine) as session, session.begin():
        rows = create_rows(session)
        yield session, rows
        session.rollback()


def assert_identity_rejected(session, table, row_id):
    with pytest.raises(IntegrityError, match='immutable'):
        with session.begin_nested():
            session.execute(text(f'UPDATE {table} SET public_id = :value WHERE id = :id'),
                            {'value': str(uuid4()), 'id': row_id})


@pytest.mark.parametrize('table', ENTITIES)
@pytest.mark.parametrize('operation', ['insert', 'legitimate_update', 'public_id_update'])
def test_identity_matrix(identity_rows, table, operation):
    session, rows = identity_rows
    row = rows[table]
    if operation == 'public_id_update':
        assert_identity_rejected(session, table, row.id)
    elif operation == 'legitimate_update':
        session.execute(text(f'UPDATE {table} SET remarks = :value WHERE id = :id'),
                        {'value': 'legitimate annotation', 'id': row.id})
        assert session.scalar(text(f'SELECT remarks FROM {table} WHERE id = :id'), {'id': row.id}) == 'legitimate annotation'
        # Assigning the identical identity is not a change and must still work.
        session.execute(text(f'UPDATE {table} SET public_id = public_id WHERE id = :id'), {'id': row.id})
    else:
        assert session.scalar(text(f'SELECT public_id FROM {table} WHERE id = :id'), {'id': row.id}) == row.public_id


@pytest.mark.parametrize('table', ADDED)
def test_removing_each_guard_breaks_the_rejection_test(identity_rows, table):
    session, rows = identity_rows
    name = f'{table}_identity_immutable_update'
    suffix = f' ON {table}' if session.get_bind().dialect.name == 'postgresql' else ''
    # Savepoint rollback restores the trigger even on SQLite.
    savepoint = session.begin_nested()
    try:
        session.execute(text(f'DROP TRIGGER {name}{suffix}'))
        with pytest.raises(pytest.fail.Exception, match='DID NOT RAISE'):
            assert_identity_rejected(session, table, rows[table].id)
    finally:
        savepoint.rollback()


def test_system_birth_identity_and_constraints(identity_rows):
    from dem.errors import ConflictError, ValidationError
    from dem.identity import new_entity_public_id
    session, rows = identity_rows
    dem = DemServices(session)
    first = rows['axiom_system']
    second = dem.axioms.register_system(first.name, namespace='test.other')
    assert first.public_id != second.public_id
    explicit = dem.axioms.register_system('moved', namespace='test.other', public_id_key='test.birth::original')
    assert explicit.public_id == new_entity_public_id('axiom_system', 'test.birth', 'original', None)
    with pytest.raises(ConflictError):
        dem.axioms.register_system('another', public_id_key='test.birth::original')
    with pytest.raises(ValidationError):
        dem.axioms.register_system('bad-key', public_id_key='not-a-key')
    for value in (None, second.public_id):
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(text('INSERT INTO axiom_system (public_id, namespace_id, name) VALUES (:value, :namespace, :name)'),
                                {'value': value, 'namespace': first.namespace_id, 'name': 'invalid-' + str(uuid4())})
    assert dem.axioms.get_system_by_public_id(first.public_id).id == first.id


def test_system_cold_and_upgrade_identity_match(tmp_path):
    with _empty_database_pair(tmp_path) as (migration, model):
        _migrate(migration.url, '20261008_0001')
        with migration.begin() as connection:
            namespace_id = connection.scalar(text("SELECT id FROM namespace ORDER BY id LIMIT 1"))
            namespace = connection.scalar(text('SELECT name FROM namespace WHERE id=:id'), {'id': namespace_id})
            connection.execute(text("INSERT INTO axiom_system (namespace_id, name, remarks) VALUES (:namespace, 'portable-system', 'preserved')"), {'namespace': namespace_id})
        _migrate(migration.url, 'head')
        Base.metadata.create_all(model)
        with Session(model) as session:
            cold = DemServices(session).axioms.register_system('portable-system', namespace=namespace)
            with migration.connect() as connection:
                row = connection.execute(text('SELECT public_id, remarks FROM axiom_system')).one()
                assert row.public_id == cold.public_id
                assert row.remarks == 'preserved'
                assert not next(c for c in inspect(connection).get_columns('axiom_system') if c['name'] == 'public_id')['nullable']


def _api_request(dem, method, path, body=None):
    import asyncio
    import json
    from fastapi import FastAPI
    from webapi.deps import dem_services
    from webapi.routers.axioms import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dem_services] = lambda: dem
    async def request():
        payload = json.dumps(body).encode() if body is not None else b''
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': payload, 'more_body': False}
        async def send(message):
            messages.append(message)
        await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                   'method': method, 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                   'root_path': '', 'query_string': b'',
                   'headers': [(b'content-type', b'application/json')],
                   'server': ('test', 80), 'client': ('test', 1)}, receive, send)
        status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
        content = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
        return status, json.loads(content)
    return asyncio.run(request())


def test_system_rest_public_identity_cannot_be_chosen(identity_rows):
    from dem.identity import new_entity_public_id
    from webapi.deps import LOCAL_WORKSPACE_NAMESPACE
    session, _ = identity_rows
    dem = DemServices(session)
    status, row = _api_request(dem, 'POST', '/axiom-systems', {
        'name': 'api-system', 'public_id_key': 'test.stolen::identity',
        'public_id': '00000000-0000-0000-0000-000000000000',
    })
    # Like other create schemas, unknown fields are ignored, never forwarded.
    assert status == 201
    assert row['public_id'] == new_entity_public_id('axiom_system', LOCAL_WORKSPACE_NAMESPACE, 'api-system', None)
    for ref in (str(row['id']), row['public_id']):
        status, fetched = _api_request(dem, 'GET', f'/axiom-systems/{ref}')
        assert status == 200
        assert fetched == row


def test_export_system_identity_and_reference_closure(identity_rows, tmp_path):
    import json
    from zipfile import ZipFile
    from webapi.workspace_export import write_workspace_export, WorkspaceExportMetadata
    session, rows = identity_rows
    dem = DemServices(session)
    second = dem.axioms.register_system(rows['axiom_system'].name, namespace='test.other')
    dem.axioms.add_to_system(second.id, rows['axiom'].id)
    destination = tmp_path / 'identity.dempkg'
    write_workspace_export(session, destination, WorkspaceExportMetadata(package='test.identity', description='Public identity regression'))
    with ZipFile(destination) as archive:
        systems = [json.loads(line) for line in archive.read('axiom_systems.jsonl').splitlines()]
        assert len({r['public_id'] for r in systems}) == 2
        assert {r['namespace'] for r in systems} == {'test.identity', 'test.other'}
        assert {r['name'] for r in systems} == {'identity-system'}
        members = [json.loads(line) for line in archive.read('axiom_system_members.jsonl').splitlines()]
        assert {r['axiom_system_public_id'] for r in members} == {r['public_id'] for r in systems}
        assert all(r['axiom_public_id'] == rows['axiom'].public_id for r in members)
        assert json.loads(archive.read('manifest.json'))['schema_version'] == 2


def test_existing_workspace_receives_identity_migration(tmp_path):
    from sqlalchemy import create_engine
    from test_workspace_schema_upgrade import _copy_legacy, _register_workspace, _sqlite_url
    from webapi.management.schema_upgrade import upgrade_all_workspaces
    from webapi.management.sqlite_workspace import inspect_sqlite_workspace, EXPECTED_SQLITE_TRIGGERS
    from dem.identity import new_entity_public_id
    workspace = _copy_legacy(tmp_path)
    management_url, _ = _register_workspace(tmp_path / 'management.db', workspace)
    assert upgrade_all_workspaces(management_url)[0].outcome == 'upgraded'
    assert inspect_sqlite_workspace(workspace).revision == '20261019_0002'
    engine = create_engine(_sqlite_url(workspace))
    try:
        with engine.connect() as connection:
            systems = connection.execute(text('SELECT s.id, s.public_id, s.name, n.name AS namespace FROM axiom_system s JOIN namespace n ON n.id=s.namespace_id')).all()
            assert systems
            for row in systems:
                assert row.public_id == new_entity_public_id('axiom_system', row.namespace, row.name, None)
            triggers = set(connection.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger'")))
            assert triggers == EXPECTED_SQLITE_TRIGGERS
        with Session(engine) as session:
            assert_identity_rejected(session, 'axiom_system', systems[0].id)
        assert upgrade_all_workspaces(management_url)[0].outcome == 'ready'
    finally:
        engine.dispose()
