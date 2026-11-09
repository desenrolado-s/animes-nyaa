"""Temporary loopback-only OAuth redirect receiver for MyAnimeList."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time
from urllib.parse import urlparse

from .myanimelist import callback_code


class CallbackListener:
    def __init__(self, redirect_uri, state, on_code, success_message, error_message, timeout=300):
        parsed = urlparse(redirect_uri)
        if (parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1')
                or not parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('Automatic callback requires an HTTP loopback URL with an explicit port')
        self.redirect_uri, self.state, self.on_code = redirect_uri, state, on_code
        self.expected_host = parsed.netloc.lower()
        self.success_message, self.error_message = success_message, error_message
        self.timeout = timeout
        self.stopped = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(2)

            def log_message(self, *_args):
                pass  # Never log authorization codes.

            def do_GET(self):
                try:
                    if self.headers.get('Host', '').lower() != owner.expected_host:
                        raise ValueError('Invalid host')
                    code = callback_code(f'{parsed.scheme}://{parsed.netloc}{self.path}',
                                         owner.redirect_uri, owner.state)
                except ValueError:
                    self.send_response(400)
                    message = owner.error_message
                else:
                    self.send_response(200)
                    message = owner.success_message
                    owner.stopped.set()
                    owner.on_code(code)
                body = ('<!doctype html><html><head><meta charset="utf-8"><title>MyAnimeList</title>'
                        '</head><body><p>' + message + '</p></body></html>').encode('utf-8')
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()
                self.wfile.write(body)

        self.server = HTTPServer(('127.0.0.1', parsed.port), Handler)
        self.server.timeout = 0.25
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        deadline = time.monotonic() + self.timeout
        try:
            while not self.stopped.is_set() and time.monotonic() < deadline:
                self.server.handle_request()
        finally:
            self.server.server_close()

    def close(self):
        self.stopped.set()
        if threading.current_thread() is not self.thread:
            self.thread.join(timeout=1)
