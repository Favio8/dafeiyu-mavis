"""Manual M2 fixture server. This is test infrastructure, not product IPC."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> None:
    """Serve only the dedicated fixture directory on a random loopback port."""
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/mavis"
    handler = partial(SimpleHTTPRequestHandler, directory=str(fixture))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        print(f"TEST ONLY: http://127.0.0.1:{server.server_port}/controlled.html?seed=17", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
