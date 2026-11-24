#!/usr/bin/env python3
# Receptor de fotogramas del escáner (solo biblioteca estándar).
# POST /upload/<sesión>/<archivo> guarda el cuerpo en /data/<sesión>/<archivo>.
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.environ.get("DATA_DIR", "/data")
MAX_BYTES = 8 * 1024 * 1024
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
FILE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        parts = self.path.split("?")[0].strip("/").split("/")
        if len(parts) != 3 or parts[0] != "upload" or not SESSION_RE.match(parts[1]) or not FILE_RE.match(parts[2]):
            return self.reply(404, "ruta no válida", close=True)
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return self.reply(411, "falta Content-Length", close=True)
        if n > MAX_BYTES:
            return self.reply(413, "archivo demasiado grande", close=True)
        body = self.rfile.read(n)
        folder = os.path.join(ROOT, parts[1])
        os.makedirs(folder, exist_ok=True)
        tmp = os.path.join(folder, parts[2] + ".part")
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, os.path.join(folder, parts[2]))  # escritura completa o nada
        self.reply(201, "ok")

    def reply(self, code, msg, close=False):
        data = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
