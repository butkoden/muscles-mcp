import json
import sys
import types

from muscles.core import ApplicationMeta, BaseStrategy, Context

from muscles_mcp import (
    McpAdapter,
    McpStrategy,
    make_mcp_asgi_app,
    make_mcp_cli_command,
    make_mcp_wsgi_app,
    make_protocol_app,
)


class _EchoStrategy:
    def execute(self, *args, **kwargs):
        return kwargs


def _build_app():
    class _App(metaclass=ApplicationMeta):
        context = Context(_EchoStrategy)

    app = _App()

    @app.action(
        name="ping",
        input_schema={"type": "object", "properties": {}},
    )
    def ping(payload, context):
        return {"pong": True}

    return app


def test_make_protocol_app_builds_mcp_http_apps():
    app = _build_app()
    asgi_entrypoint = make_protocol_app(app, "mcp-asgi")
    wsgi_entrypoint = make_protocol_app(app, "mcp-wsgi", "/_mcp")
    cli_entrypoint = make_protocol_app(app, "mcp-cli")

    assert callable(asgi_entrypoint)
    assert callable(wsgi_entrypoint)
    assert callable(cli_entrypoint)


def test_make_protocol_app_builds_mcp_entrypoint_and_uses_mcp_strategy():
    app = _build_app()
    entrypoint = make_protocol_app(app, "mcp")

    assert isinstance(entrypoint, McpAdapter)


def test_make_protocol_app_can_use_named_context():
    class _McpNamedContextApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)
        asgi = Context(_EchoStrategy, transport="asgi")
        mcp_private = Context(_EchoStrategy, transport="asgi")

    app = _McpNamedContextApp()

    @app.action(
        name="ping",
        input_schema={"type": "object", "properties": {}},
    )
    def ping(payload, context):
        return {"pong": True}

    entrypoint = make_protocol_app(app, "mcp", context="mcp_private")

    assert isinstance(entrypoint, McpAdapter)
    assert entrypoint.context is app.mcp_private


def test_make_protocol_app_builds_asgi_entrypoint_after_dynamic_protocol_switch(monkeypatch):
    class FakeAsgiStrategy:
        pass

    def fake_asgi_app(app, context=None):
        return ("asgi-entry", app, context)

    fake_module = types.ModuleType("muscles.asgi")
    fake_module.AsgiStrategy = FakeAsgiStrategy
    fake_module.asgi_app = fake_asgi_app
    monkeypatch.setitem(sys.modules, "muscles.asgi", fake_module)

    app = _build_app()
    entrypoint = make_protocol_app(app, "asgi")

    assert entrypoint == ("asgi-entry", app, app.context)


def test_make_protocol_app_builds_wsgi_entrypoint_from_wsgi_context():
    class WsgiContext(BaseStrategy):
        def execute(self, *args, **kwargs):
            environ = kwargs.get("environ")
            start_response = kwargs.get("start_response")
            if start_response is not None:
                start_response("200 OK", [])
            return [f"path:{environ.get('PATH_INFO')}".encode()]

    class _WsgiApp(metaclass=ApplicationMeta):
        wsgi = Context(WsgiContext, transport="wsgi")

    app = _WsgiApp()

    entrypoint = make_protocol_app(app, "wsgi")
    status = None
    headers = None

    def start_response(s, h):
        nonlocal status, headers
        status, headers = s, h

    response = entrypoint({"PATH_INFO": "/ping"}, start_response)

    assert response == [b"path:/ping"]
    assert status == "200 OK"
    assert headers == []


def test_make_protocol_app_rejects_unknown_protocol():
    app = _build_app()

    try:
        make_protocol_app(app, "invalid")
    except ValueError as exc:
        assert "mcp" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_make_mcp_asgi_app_processes_call_tool_request():
    app = _build_app()
    asgi_app = make_mcp_asgi_app(app)

    async def receive():
        return {"type": "http.request", "body": b'{"operation":"call_tool","name":"ping","arguments":{}}', "more_body": False}

    response_started = {}
    chunks = []

    async def send(message):
        if message["type"] == "http.response.start":
            response_started.update(message)
        elif message["type"] == "http.response.body":
            chunks.append(message["body"])

    import asyncio

    asyncio.run(asgi_app({"type": "http", "method": "POST", "path": "/mcp"}, receive, send))

    body = b"".join(chunks)
    payload = json.loads(body.decode("utf-8"))
    assert response_started["status"] == 200
    assert payload == {"content": [{"type": "json", "json": {"pong": True}}]}


def test_make_mcp_wsgi_app_processes_list_resources_request():
    app = _build_app()
    wsgi_app = make_mcp_wsgi_app(app)

    status = None
    headers = None

    def start_response(s, h):
        nonlocal status, headers
        status, headers = s, h

    import io

    environ = {
        "PATH_INFO": "/mcp",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": "53",
        "wsgi.input": io.BytesIO(b'{"operation":"list_resources"}'),
    }

    response = b"".join(wsgi_app(environ, start_response))
    payload = json.loads(response.decode("utf-8"))

    assert status == "200 OK"
    assert headers[0][0] == "Content-Type"
    assert payload and payload[0]["uri"] == "muscles://app/inspect"


def test_make_mcp_cli_command_executes_operation():
    app = _build_app()
    command = make_mcp_cli_command(app)

    result = command({"operation": "list_tools"})
    assert [item["name"] for item in result] == ["ping"]


def test_make_mcp_cli_command_rejects_non_object_payload():
    app = _build_app()
    command = make_mcp_cli_command(app)

    result = command(["not-an-object"])

    assert result["isError"] is True
    assert result["error"]["code"] == "invalid_request"
    assert "JSON object" in result["error"]["message"]
