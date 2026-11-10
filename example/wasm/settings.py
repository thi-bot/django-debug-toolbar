"""Settings for running the example project in the browser, with Pyodide.

See example/wasm/README.rst for how this works.
"""

from example.settings import *  # noqa: F403
from example.settings import INSTALLED_APPS, MIDDLEWARE

# The data directory is backed by IndexedDB, so it survives the service
# worker being stopped and restarted by the browser.
DATA_DIR = "/data"

ALLOWED_HOSTS = ["*"]

# Relative, so it follows the SCRIPT_NAME when hosted under a sub-path.
STATIC_URL = "static/"

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "daphne"]

# Static files are served by Django's StaticFilesHandler instead.
MIDDLEWARE = [
    "example.wasm.middleware.KeepAliveMiddleware",
    *(m for m in MIDDLEWARE if m != "whitenoise.middleware.WhiteNoiseMiddleware"),
]

ROOT_URLCONF = "example.wasm.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": f"{DATA_DIR}/db.sqlite3",
    }
}

PASSWORD_HASHERS = [
    # The default PBKDF2 iterations are slow under WebAssembly.
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


def show_toolbar(request):
    # Requests have no meaningful REMOTE_ADDR here, so skip INTERNAL_IPS.
    return True


DEBUG_TOOLBAR_CONFIG = {
    "ROOT_TAG_EXTRA_ATTRS": "data-turbo-permanent hx-preserve",
    "SHOW_TOOLBAR_CALLBACK": show_toolbar,
    # Python state is lost whenever the browser stops the service worker,
    # so keep the toolbar's history in the (persisted) database.
    "TOOLBAR_STORE_CLASS": "debug_toolbar.store.DatabaseStore",
}
