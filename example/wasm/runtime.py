"""Runs inside Pyodide, in the service worker. Not meant for a regular server.

``setup()`` prepares Django and the database, then ``handle_request()`` is
called by the service worker (sw.js) for each intercepted browser request.
"""

import io
import os
import sys
from urllib.parse import urlsplit

DEMO_USERNAME = "admin"
DEMO_PASSWORD = "admin"

_application = None


def setup():
    global _application

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example.wasm.settings")
    # Pyodide always has a running event loop, which makes Django think it's
    # in an async context and refuse to run database queries.
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

    import django

    django.setup()

    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application

    os.makedirs(settings.DATA_DIR, exist_ok=True)
    call_command("migrate", interactive=False, verbosity=0)

    User = get_user_model()
    if not User.objects.filter(username=DEMO_USERNAME).exists():
        User.objects.create_superuser(DEMO_USERNAME, "", DEMO_PASSWORD)

    _application = StaticFilesHandler(get_wsgi_application())


def handle_request(method, url, script_name, headers, body):
    """Run a request through Django's WSGI handler.

    ``headers`` is a JS object proxy (name -> value), ``body`` a Uint8Array
    proxy or None. Returns a dict with ``status``, ``headers`` and ``body``.
    """
    parts = urlsplit(url)
    path = parts.path
    script_name = script_name.rstrip("/")
    if script_name and path.startswith(script_name):
        path = path[len(script_name) :]
    body = body.to_bytes() if body is not None else b""

    environ = {
        "REQUEST_METHOD": method,
        "SCRIPT_NAME": script_name,
        "PATH_INFO": path or "/",
        "QUERY_STRING": parts.query,
        "SERVER_NAME": parts.hostname,
        "SERVER_PORT": str(parts.port or (443 if parts.scheme == "https" else 80)),
        "SERVER_PROTOCOL": "HTTP/1.1",
        "REMOTE_ADDR": "127.0.0.1",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": parts.scheme,
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": sys.stderr,
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    for name, value in headers.to_py().items():
        key = name.upper().replace("-", "_")
        if key == "CONTENT_TYPE":
            environ["CONTENT_TYPE"] = value
        elif key != "CONTENT_LENGTH":
            environ[f"HTTP_{key}"] = value

    response = {}

    def start_response(status, response_headers, exc_info=None):
        response["status"] = int(status.split(" ", 1)[0])
        response["headers"] = [list(header) for header in response_headers]

    result = _application(environ, start_response)
    try:
        response["body"] = b"".join(result)
    finally:
        if hasattr(result, "close"):
            result.close()
    return response
