"""Serve the click-to-call demo on the local network without dependencies."""

import http.server
import os
import socket


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("8.8.8.8", 80))
            return str(connection.getsockname()[0])
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("http://localhost:8000")
    print(f"http://{lan_ip()}:8000")
    http.server.ThreadingHTTPServer(("0.0.0.0", 8000), http.server.SimpleHTTPRequestHandler).serve_forever()
