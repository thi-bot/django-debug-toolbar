In-browser demo
===============

This runs the example project, with the debug toolbar, entirely in the
browser: Python and Django run in WebAssembly with
`Pyodide <https://pyodide.org/>`_, and the database is a SQLite file stored in
the browser. Once built, it's a static site that can be hosted anywhere.

It's inspired by `django_webassembly
<https://github.com/m-butterfield/django_webassembly>`_.

Running it
----------

From the repository root, with `uv <https://docs.astral.sh/uv/>`_ installed::

    $ make example_wasm

Then open http://localhost:8000/. The admin's username and password are both
``admin``. Run the command again to rebuild after changing the toolbar or the
example project: the page reloads with the new version.

To build the static site without serving it, in ``example/wasm/build/``::

    $ python example/wasm/build.py

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
