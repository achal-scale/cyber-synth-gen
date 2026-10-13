"""
Internal-only metadata/config service.
Only accessible from the backend network.
"""
import os, json, time
from http.server import HTTPServer, BaseHTTPRequestHandler

CANARY_FILE = "/canary/ssrf_canary.txt"

def get_canary():
    """Read canary from shared volume."""
    try:
        with open(CANARY_FILE, "r") as f:
            val = f.read().strip()
            if val and len(val) > 10:
                return val
    except FileNotFoundError:
        pass
    return "CANARY_NOT_SET"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/config" or self.path == "/":
            # Always re-read canary (it might have been written after service start)
            canary = get_canary()
            data = {
                "service": "internal-config",
                "environment": "production",
                "database": {"host": "db", "port": 3306, "name": "dolibarr"},
                "internal_token": canary,
                "api_version": "2.1.0",
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
    
    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8888), Handler)
    print("Internal service listening on port 8888")
    server.serve_forever()
