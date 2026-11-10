import re

# Browsers stop idle service workers after ~30 seconds, and starting Python
# again takes a while. Pinging the worker from open pages keeps it running.
KEEPALIVE_SCRIPT = """<script>
setInterval(() => navigator.serviceWorker.controller?.postMessage("keepalive"), 20000);
</script>"""

BODY_END = re.compile(r"</body>", re.IGNORECASE)


class KeepAliveMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            response.get("Content-Type", "").startswith("text/html")
            and not response.streaming
            and not response.get("Content-Encoding")
        ):
            content = response.content.decode(response.charset)
            parts = BODY_END.split(content)
            if len(parts) > 1:
                parts[-2] += KEEPALIVE_SCRIPT
                response.content = "</body>".join(parts)
                if "Content-Length" in response:
                    response["Content-Length"] = len(response.content)
        return response
