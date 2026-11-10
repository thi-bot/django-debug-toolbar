from example.urls import urlpatterns as example_urlpatterns

# Async views need threads to run under WSGI, which Pyodide doesn't have.
ASYNC_VIEWS = {"async_home", "async_db", "async_db_concurrent"}

urlpatterns = [
    pattern
    for pattern in example_urlpatterns
    if getattr(pattern, "name", None) not in ASYNC_VIEWS
]
