"""Serial real-uvicorn availability regressions; no Caddy or remote services."""
import asyncio

import pytest
from beta2_support import base_api
from beta_fixture import base_phase
from beta_uvicorn import Clients, A, docker_command, low_rate, server

SEED_PHASE = base_phase()
SEED_DATABASE = "sqlite"
pytestmark = pytest.mark.timing_sensitive


@pytest.mark.parametrize("readers", [36,64])
def test_one_source_cannot_hold_the_transport_limit(base_api,tmp_path,readers):
    command=docker_command()
    limit=int(command[command.index("--limit-concurrency")+1])
    with server(base_api,tmp_path/"uvicorn.log") as (port,_):
        result=asyncio.run(low_rate(port,readers,limit))
    assert all(row["status"]==200 and row["seconds"]<2 for row in result["b"]),result
    if readers==64:
        assert any(row["status"]==429 for row in result["a_completed"])


def test_home_33_parallel_reads_are_not_rejected(base_api,tmp_path):
    async def read(port):
        clients=Clients(port)
        try:
            return await asyncio.gather(*(clients.request(A) for _ in range(33)))
        finally:
            await clients.close()
    with server(base_api,tmp_path/"uvicorn-home.log") as (port,_):
        result=asyncio.run(read(port))
    assert len(result)==33 and all(row["status"]==200 for row in result),result
