"""Real server harness; the application, seed validation and HTTP stack are real."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
A, B = "198.51.100.11", "198.51.100.12"


def docker_command():
    return json.loads(next(line[4:] for line in (ROOT/"deploy/beta/api.Dockerfile").read_text().splitlines()
                           if line.startswith("CMD ")))


@contextmanager
def server(api, log_path, limit=None):
    command = docker_command()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command[command.index("--port")+1] = str(port)
    command[command.index("--forwarded-allow-ips")+1] = "127.0.0.1"
    if limit is not None:
        command[command.index("--limit-concurrency")+1] = str(limit)
    env = {key:value for key,value in os.environ.items() if not key.startswith("DEM_")}
    env.update(DEM_BETA="1", DEM_DATABASE_URL=api.engine.url.render_as_string(hide_password=False),
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    executable = sys.executable
    if os.name == "nt":
        # Run the actual interpreter directly while retaining the same venv.
        # This avoids a redirector parent outliving/killing the wrong process.
        executable = sys._base_executable
        env["__PYVENV_LAUNCHER__"] = sys.executable
    with log_path.open("wb") as log:
        process = subprocess.Popen([executable,"-B","-m",*command],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+15
            while True:
                if process.poll() is not None:
                    raise RuntimeError(log_path.read_text(encoding="utf-8"))
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.5) as connection:
                        connection.sendall(b"GET /health/ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                        if b" 200 " in connection.recv(1024):
                            break
                except OSError:
                    pass
                if time.monotonic()>deadline:
                    raise TimeoutError("Server startup timed out")
                time.sleep(.03)
            yield port, process
        finally:
            process.kill()
            process.wait(timeout=5)


class Clients:
    def __init__(self, port):
        self.port, self.writers, self.tasks = port, [], []

    async def connect(self):
        reader, writer = await asyncio.open_connection("127.0.0.1",self.port)
        self.writers.append(writer)
        return reader, writer

    @staticmethod
    def headers(source, slow=False, keep=False):
        return (("POST /formulas" if slow else "GET /stats") + " HTTP/1.1\r\nHost: localhost\r\n"
                + f"X-Forwarded-For: {source}\r\n"
                + ("Content-Length: 262144\r\nContent-Type: application/json\r\n" if slow else "")
                + ("Connection: keep-alive\r\n\r\n" if keep else "Connection: close\r\n\r\n")).encode()

    async def request(self, source):
        start = time.perf_counter()
        reader, writer = await self.connect()
        writer.write(self.headers(source))
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(),12)
        return {"status":int(raw.split(b" ",2)[1]),"seconds":time.perf_counter()-start,
                "body":raw.split(b"\r\n\r\n",1)[1].decode(errors="replace")}

    async def close(self):
        for writer in self.writers:
            writer.close()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)


async def low_rate(port, readers, limit):
    clients=Clients(port)
    try:
        for _ in range(4):
            _,writer=await clients.connect()
            writer.write(clients.headers(A,slow=True)+b"{")
            await writer.drain()
            await asyncio.sleep(.03)
        queued=min(32,limit-5)
        for _ in range(queued):
            reader,writer=await clients.connect()
            writer.write(clients.headers(A))
            await writer.drain()
            clients.tasks.append(asyncio.create_task(reader.read()))
            await asyncio.sleep(.005)
        overflow=[]
        for _ in range(readers-queued):
            task=asyncio.create_task(clients.request(A))
            overflow.append(task)
            clients.tasks.append(task)
        await asyncio.sleep(.1)
        results=[]
        for _ in range(10):
            results.append(await clients.request(B))
            await asyncio.sleep(.01)
        return {"b":results,"a_completed":[task.result() for task in overflow if task.done() and not task.cancelled()]}
    finally:
        await clients.close()
