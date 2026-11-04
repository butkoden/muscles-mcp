from __future__ import annotations

import json
import sys
from typing import Any

from .adapter import McpPayload
from .adapter import McpAdapter, resolve_mcp_context


class ProtocolUnavailableError(RuntimeError):
    """Raised when requested transport protocol package is not installed."""


def _as_json_response(payload: McpPayload, start_response) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if start_response is not None:
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        )
    return [body]


def _coerce_request_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    raise ValueError("MCP request payload must be a JSON object")


def _read_json_body(stream, length: int | None = None) -> dict[str, Any]:
    raw = stream.read() if not length else stream.read(length)
    if not raw:
        return {}
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    try:
        return _coerce_request_payload(json.loads(raw.decode("utf-8")))
    except Exception as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc


def _coerce_payload_from_exception(exc: Exception) -> dict[str, Any]:
    from .adapter import McpError

    if isinstance(exc, McpError):
        return {"isError": True, "error": {"code": exc.code, "message": exc.message, "data": exc.data}}
    return {
        "isError": True,
        "error": {
            "code": "invalid_request",
            "message": str(exc),
            "data": None,
        },
    }


def _execute_mcp_payload(app, payload: dict[str, Any] | None = None, context: str | Any | None = None) -> McpPayload:
    return McpAdapter.from_application(app, context=context).execute(request=payload or None)


def make_mcp_asgi_app(app, route: str = "/mcp", context: str | Any | None = None):
    route = f"/{route.lstrip('/')}"

    async def application(scope, receive, send):
        if scope.get("type") != "http":
            await send({"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b""})
            return

        path = scope.get("path", "/")
        method = (scope.get("method") or "GET").upper()
        if path != route:
            await send({
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": b"{}"})
            return
        if method != "POST":
            await send({
                "type": "http.response.start",
                "status": 405,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": b"{}"})
            return

        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception as exc:
            response = _coerce_payload_from_exception(
                ValueError(f"Invalid MCP request JSON: {exc}")
            )
        else:
            try:
                response = _execute_mcp_payload(app, _coerce_request_payload(payload), context=context)
            except Exception as exc:
                response = _coerce_payload_from_exception(exc)

        content = json.dumps(response, ensure_ascii=False).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(content)).encode("utf-8")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": content})

    return application


def make_mcp_wsgi_app(app, route: str = "/mcp", context: str | Any | None = None):
    route = f"/{route.lstrip('/')}"

    def application(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        method = (environ.get("REQUEST_METHOD") or "GET").upper()
        if path != route:
            start_response("404 Not Found", [("Content-Type", "application/json; charset=utf-8")])
            return [b"{}"]
        if method != "POST":
            start_response("405 Method Not Allowed", [("Content-Type", "application/json; charset=utf-8")])
            return [b"{}"]

        length = 0
        raw_length = environ.get("CONTENT_LENGTH") or 0
        try:
            if raw_length:
                length = int(raw_length)
        except (TypeError, ValueError):
            length = 0

        stream = environ.get("wsgi.input", sys.stdin.buffer)
        try:
            payload = _read_json_body(stream, length or None)
        except Exception as exc:
            response = _coerce_payload_from_exception(exc)
            return _as_json_response(response, start_response)

        try:
            response = _execute_mcp_payload(app, payload, context=context)
        except Exception as exc:
            response = _coerce_payload_from_exception(exc)
        return _as_json_response(response, start_response)

    return application


def make_mcp_cli_command(app, context: str | Any | None = None):
    """Return a callable that executes one MCP request from JSON payload."""

    def command(payload: dict[str, Any] | None = None, **kwargs):
        try:
            if payload is None:
                payload = json.loads(sys.stdin.read() or "{}")
            payload = _coerce_request_payload(payload)
            if kwargs:
                payload = {**payload, **kwargs}
            response = _execute_mcp_payload(app, payload, context=context)
        except Exception as exc:
            response = _coerce_payload_from_exception(exc)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return response

    return command


def _resolve_protocol_context(app, protocol: str, context: str | Any | None = None):
    return resolve_mcp_context(
        app,
        context=context,
        transport=protocol,
        default="context",
    )


def make_protocol_app(app, protocol: str, route: str = "/mcp", context: str | Any | None = None) -> Any:
    """Build a protocol-aware entrypoint for one Muscles application."""

    protocol = protocol.lower()

    if protocol == "mcp":
        return McpAdapter.from_application(app, context=context)

    if protocol == "mcp-asgi":
        return make_mcp_asgi_app(app, route=route, context=context)

    if protocol == "mcp-wsgi":
        return make_mcp_wsgi_app(app, route=route, context=context)

    if protocol == "mcp-cli":
        return make_mcp_cli_command(app, context=context)

    if protocol == "asgi":
        from muscles.asgi import asgi_app

        selected_context = _resolve_protocol_context(app, "asgi", context=context)

        if selected_context is None:
            return asgi_app(app)
        if hasattr(asgi_app, "__code__") and asgi_app.__code__.co_argcount >= 2:
            return asgi_app(app, context=selected_context)
        return asgi_app(app)

    if protocol == "wsgi":
        selected_context = _resolve_protocol_context(app, "wsgi", context=context)

        if selected_context is None:
            raise ProtocolUnavailableError("WSGI protocol requested, but no WSGI context found on app.")

        def application(environ, start_response):
            return selected_context.execute(environ=environ, start_response=start_response, container=app)

        return application

    raise ValueError(
        f"Unsupported protocol '{protocol}'. Use 'mcp', 'mcp-asgi', 'mcp-wsgi', 'mcp-cli', 'asgi', or 'wsgi'."
    )


__all__ = [
    "ProtocolUnavailableError",
    "make_mcp_asgi_app",
    "make_mcp_wsgi_app",
    "make_mcp_cli_command",
    "make_protocol_app",
]
