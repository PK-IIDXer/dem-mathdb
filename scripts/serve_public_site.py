"""Local verification server: page index first, existing file, then SPA fallback.

This loopback-only helper does not proxy /api; use Caddy for integration with API.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse


class PublicSiteHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".xml": "application/xml", ".txt": "text/plain"}

    def translate_path(self, path):
        candidate = Path(super().translate_path(path))
        root = Path(self.directory).resolve()
        if not candidate.resolve().is_relative_to(root):
            return str(root / "index.html")
        if (candidate / "index.html").is_file():
            return str(candidate / "index.html")
        if candidate.is_file():
            return str(candidate)
        return str(root / "index.html")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                partial(PublicSiteHandler, directory=str(args.directory.resolve())))
    print(f"Serving http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
