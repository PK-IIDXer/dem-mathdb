"""Public cache cleanup must leave unrelated private-style databases intact."""
import os
import uuid
import pytest
from conftest import PostgreSQLSeedSnapshotFactory

pytestmark = pytest.mark.skipif(os.environ.get("DEM_TEST_DATABASE") != "postgresql", reason="PostgreSQL cache cleanup boundary")

def test_public_cleanup_preserves_other_database_names(seed_snapshot_factory):
    factory = seed_snapshot_factory.postgresql
    token = uuid.uuid4().hex[:20]
    private_sentinel = "seed_" + token + "_boundary"
    public_stale = "pub_seed_" + token + "_boundary"
    created = []
    try:
        for name in (private_sentinel, public_stale):
            factory._create_database(name, "template0")
            created.append(name)
        probe = PostgreSQLSeedSnapshotFactory(factory.fingerprint)
        try:
            assert probe._database_exists(private_sentinel)
            assert not probe._database_exists(public_stale)
        finally:
            probe.close()
    finally:
        for name in created:
            factory._drop_database(name)


@pytest.mark.parametrize("origin", ["alembic", "models"])
def test_cached_template_lookup_is_parallel_safe(seed_snapshot_factory, origin, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Event, Lock
    from beta_fixture import base_phase
    factory = seed_snapshot_factory.postgresql
    expected = factory.get(base_phase()) if origin == "alembic" else factory.get_model_l2()
    barrier = Barrier(4)
    state_lock = Lock()
    active = [0]
    overlaps = []
    real_update = PostgreSQLSeedSnapshotFactory._set_allow_connections
    def observed_update(probe, name, allow):
        with state_lock:
            active[0] += 1
            if active[0] > 1:
                overlaps.append(name)
        try:
            # Widen the catalog-update window without replacing its real SQL.
            Event().wait(0.03)
            return real_update(probe, name, allow)
        finally:
            with state_lock:
                active[0] -= 1
    monkeypatch.setattr(PostgreSQLSeedSnapshotFactory, "_set_allow_connections", observed_update)
    def lookup(_):
        probe = PostgreSQLSeedSnapshotFactory(factory.fingerprint)
        try:
            values = []
            for _ in range(4):
                probe.names.clear()
                barrier.wait(timeout=5)
                values.append(probe.get(base_phase()) if origin == "alembic" else probe.get_model_l2())
            return values
        finally:
            probe.close()
    with ThreadPoolExecutor(max_workers=4) as workers:
        assert list(workers.map(lookup, range(4))) == [[expected] * 4] * 4
    assert overlaps == []
    with factory.admin_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT datallowconn FROM pg_database WHERE datname = %s", (expected,)).scalar_one() is False
