In-browser demo
===============

This runs the example project, with the debug toolbar, entirely in the
browser: Python and Django run in WebAssembly with
`Pyodide <https://pyodide.org/>`_, and the database is a SQLite file stored in
the browser. Once built, it's a static site that can be hosted anywhere.

It's inspired by `django_webassembly
<https://github.com/m-butterfield/django_webassembly>`_.

Requirements
------------

- `uv <https://docs.astral.sh/uv/>`_, the only build dependency. It
  downloads Python 3.14 if needed, which must match Pyodide's Python version
  to precompile the bytecode.
- Internet access: the build downloads Django and other packages from PyPI,
  and the browser loads Pyodide from the jsDelivr CDN.
- A browser supporting module Service Workers. Tested with Chromium.

No other setup is needed, not even a virtual environment.

Running it
----------

From the repository root::

    $ make example_wasm

Or, without ``make``::

    $ uv run --no-project example/wasm/build.py --serve

Then open http://localhost:8000/. The first visit takes a few seconds while
Python starts. The admin's username and password are both ``admin``. To use
another port, pass it after ``--serve``.

To see changes to the toolbar or the example project, run the command again,
then reload the page. If it says the demo has been updated, reload once more.

Deploying it
------------

To build the static site without serving it::

    $ uv run --no-project example/wasm/build.py

Then publish the contents of ``example/wasm/build/`` with any static host,
over HTTPS. Hosting it under a sub-path, such as GitHub Pages' project
sites, is meant to work but hasn't been tested yet, and some links of the
example project assume it's at the root.

How it works
------------

- ``build.py`` builds a wheel of the toolbar from the working tree, installs
  it with its dependencies (Django…) alongside the example project, and
  precompiles all of it to Python bytecode, into a single archive.
- ``site/index.html`` registers the Service Worker, ``site/sw.js``, and shows
  its progress while it starts.
- The Service Worker loads Pyodide and the archive, then hands every request
  within its scope to Django, through the WSGI handler in ``runtime.py``.
  Requests to the demo's own files, under ``_wasm/``, aren't intercepted.
- ``settings.py`` adapts the example project's settings: the database is
  stored in a directory synced to IndexedDB, and the toolbar uses its
  database store, so data survives the browser stopping the Service Worker.

Limitations
-----------

- Browsers stop idle Service Workers after about 30 seconds, and restarting
  Python takes a few seconds. Open pages ping the worker to keep it running
  (see ``middleware.py``).
- Responses from a Service Worker can't set cookies with ``Set-Cookie``. The
  worker sets them with the Cookie Store API instead, so they aren't
  ``HttpOnly``. Without that API, cookies are kept in memory.
- Async views and the timer panel's resource usage aren't available, as
  Pyodide has no threads and no ``resource`` module.
- Service Workers require a secure context: ``localhost`` or HTTPS.
