import sys
import types

from muscles.core import ApplicationMeta, Context, register_action

from muscles_mcp import McpAdapter, McpStrategy, make_protocol_app


class _EchoStrategy:
    def execute(self, *args, **kwargs):
        return kwargs


def _build_app():
    class _App(metaclass=ApplicationMeta):
        context = Context(_EchoStrategy)

    app = _App()

    register_action(
        app,
        name="ping",
        input_schema={"type": "object", "properties": {}},
        handler=lambda payload, context: {"pong": True},
    )
    return app


def test_make_protocol_app_builds_mcp_entrypoint_and_uses_mcp_strategy():
    app = _build_app()
    entrypoint = make_protocol_app(app, "mcp")

    assert isinstance(entrypoint, McpAdapter)
    assert app.context.strategy == McpStrategy


def test_make_protocol_app_builds_asgi_entrypoint_after_dynamic_protocol_switch(monkeypatch):
    class FakeAsgiStrategy:
        pass

    def fake_asgi_app(app):
        return ("asgi-entry", app)

    fake_module = types.ModuleType("muscles.asgi")
    fake_module.AsgiStrategy = FakeAsgiStrategy
    fake_module.asgi_app = fake_asgi_app
    monkeypatch.setitem(sys.modules, "muscles.asgi", fake_module)

    app = _build_app()
    entrypoint = make_protocol_app(app, "asgi")

    assert entrypoint == ("asgi-entry", app)
    assert app.context.strategy is FakeAsgiStrategy


def test_make_protocol_app_builds_wsgi_entrypoint_after_dynamic_protocol_switch(monkeypatch):
    class FakeWsgiStrategy:
        def execute(self, environ=None, start_response=None, **kwargs):
            if start_response is not None:
                start_response("200 OK", [])
            return [f"path:{environ.get('PATH_INFO')}".encode()]

    fake_wsgi_package = types.ModuleType("muscles.wsgi")
    fake_wsgi_impl = types.ModuleType("muscles.wsgi.wsgi")
    fake_wsgi_impl.WsgiStrategy = FakeWsgiStrategy

    monkeypatch.setitem(sys.modules, "muscles.wsgi", fake_wsgi_package)
    monkeypatch.setitem(sys.modules, "muscles.wsgi.wsgi", fake_wsgi_impl)

    app = _build_app()
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
    assert app.context.strategy is FakeWsgiStrategy


def test_make_protocol_app_rejects_unknown_protocol():
    app = _build_app()

    try:
        make_protocol_app(app, "invalid")
    except ValueError as exc:
        assert "mcp" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
