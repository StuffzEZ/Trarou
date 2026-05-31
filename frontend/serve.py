#!/usr/bin/env python3
"""
Trarou Frontend Server
Serves the static UI on port 3000 (default).
Usage: python serve.py [port]
"""

import http.server
import os
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
DIR = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def log_message(self, fmt, *args):
        print("[%s] %s %s %s" % (self.log_date_time_string(), args[0], args[1], args[2]))

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print("Trarou frontend -> http://0.0.0.0:%d" % PORT)
        print("API expected at   http://10.0.0.1:8000")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")
