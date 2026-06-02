from __future__ import annotations

from typing import Any

from .adapter import McpAdapter
from .strategy import McpStrategy


class ProtocolUnavailableError(RuntimeError):
    """Raised when requested transport protocol package is not installed."""


def _set_strategy(app, protocol: str) -> None:
    if protocol == "mcp":
        app.context.strategy = McpStrategy
        return

    if protocol == "asgi":
        try:
            from muscles.asgi import AsgiStrategy
        except Exception as exc:
            raise ProtocolUnavailableError(
                "ASGI protocol requested, but 'muscles-asgi' is not installed."
            ) from exc
        app.context.strategy = AsgiStrategy
        return

    if protocol == "wsgi":
        try:
            from muscles.wsgi.wsgi import WsgiStrategy
        except Exception as exc:
            raise ProtocolUnavailableError(
                "WSGI protocol requested, but 'muscles-wsgi' is not installed."
            ) from exc
        app.context.strategy = WsgiStrategy
        return

    raise ValueError(f"Unsupported protocol '{protocol}'. Use 'mcp', 'asgi', or 'wsgi'.")


def make_protocol_app(app, protocol: str) -> Any:
    """Build a protocol-aware entrypoint for one Muscles application.

    The same application instance can be reused across protocols. Use this helper
    to configure protocol strategy in-place and obtain the corresponding runtime
    entrypoint.
    """

    protocol = protocol.lower()
    if protocol == "mcp":
        _set_strategy(app, protocol)
        return McpAdapter.from_application(app)

    if protocol == "asgi":
        from muscles.asgi import asgi_app

        _set_strategy(app, protocol)
        return asgi_app(app)

    if protocol == "wsgi":
        _set_strategy(app, protocol)

        def application(environ, start_response):
            return app.context.execute(environ=environ, start_response=start_response)

        return application

    raise ValueError(f"Unsupported protocol '{protocol}'. Use 'mcp', 'asgi', or 'wsgi'.")


__all__ = [
    "ProtocolUnavailableError",
    "make_protocol_app",
]
