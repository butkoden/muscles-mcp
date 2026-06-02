from __future__ import annotations

import re
from typing import Any, Callable

from muscles.core import register_action

from .utils import build_model_json_schema


def _normalize_path(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    path = re.sub(r"/{2,}", "/", path)
    return "/" if path == "/" else path.rstrip("/")


def _join_path(base: str, path: str) -> str:
    if not base or base == "/":
        return path
    base = _normalize_path(base)
    if not path or path == "/":
        return base
    return f"{base}/{path.lstrip('/')}"


def _normalize_action_name(value: str) -> str:
    cleaned = re.sub(r"[{}]", "", value.strip())
    cleaned = cleaned.strip("/")
    cleaned = re.sub(r"[^0-9a-zA-Z_./-]", "", cleaned)
    cleaned = cleaned.replace("/", ".").replace("-", "_")
    return cleaned or "mcp_action"


def _normalize_server_name(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip().strip("/")
    return value or None


def _normalize_server_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        return []

    return [item for item in (_normalize_server_name(v) for v in values) if item]


def _coerce_model_schema(schema: Any) -> Any:
    if schema is None:
        return None
    if isinstance(schema, type) and hasattr(schema, "columns"):
        return build_model_json_schema(schema)
    if hasattr(schema, "columns"):
        return build_model_json_schema(schema.__class__)
    return schema


class _BoundMcpRouter:
    def __init__(self, app, router: "McpRouter"):
        self._app = app
        self._router = router

    def action(self, **kwargs):
        return self._router._decorate_action(self._app, **kwargs)

    def server(self, **kwargs):
        return self._router._build_server(self._app, **kwargs)

    def __call__(self, func: Callable | None = None, **kwargs):
        if func is not None and callable(func):
            return self.action()(func)
        if func is not None and kwargs:
            raise TypeError("Use @app_instance.mcp(...), where app_instance is a Muscles application instance")
        return self.action(**kwargs)


class _BoundMcpServer:
    def __init__(self, app, server: "McpServer"):
        self._app = app
        self._server = server

    def action(self, **kwargs):
        return self._server._decorate_action(self._app, **kwargs)

    def __call__(self, func: Callable | None = None, **kwargs):
        if func is not None and kwargs:
            raise TypeError("@app.mcp.server(...): pass-through decorator does not accept args")
        if func is not None and not callable(func):
            raise TypeError("Invalid MCP server decorator usage")
        if func is not None and callable(func):
            return self
        return self.action(**kwargs)


class McpServer:
    def __init__(
        self,
        *,
        route_prefix: str = "/",
        transports: list[str] | None = None,
        name: str | None = None,
        profile: str | None = None,
        token: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.route_prefix = _normalize_path(route_prefix)
        self.transports = list(transports or ["mcp"])
        self.name = _normalize_server_name(name) or "default"
        self.profile = _normalize_server_name(profile) or self.name
        self.token = token
        self.metadata = dict(metadata or {})

    def _decorate_action(self, app, **kwargs):
        def decorator(func):
            return self._decorate_action_func(app, func, **kwargs)

        return decorator

    def _decorate_action_func(self, app, func, **kwargs):
        route = _normalize_path(kwargs.get("route") or kwargs.get("path") or "/")
        name = kwargs.get("name")
        if not name:
            if kwargs.get("route") or kwargs.get("path"):
                name = _normalize_action_name(route)
            else:
                name = _normalize_action_name(func.__name__)

        description = kwargs.get("description") or (func.__doc__ or "").strip()
        input_schema = _coerce_model_schema(kwargs.get("input_schema"))
        output_schema = _coerce_model_schema(kwargs.get("output_schema"))

        raw_metadata = dict(kwargs.get("metadata") or {})
        action_mcp_metadata = dict(self.metadata.get("mcp", {}))
        action_mcp_metadata.update(raw_metadata.get("mcp", {}) or {})

        action_mcp_metadata.setdefault("route", route)
        action_mcp_metadata.setdefault("full_route", _join_path(self.route_prefix, route))
        action_mcp_metadata.setdefault("name", name)
        action_mcp_metadata.setdefault("transport", "/".join(self.transports))

        action_mcp_metadata.setdefault("server", self.name)
        servers = _normalize_server_list(action_mcp_metadata.get("servers"))
        if self.name not in servers:
            servers.append(self.name)
        action_mcp_metadata["servers"] = servers

        if self.profile:
            action_mcp_metadata.setdefault("profile", self.profile)
        if self.token is not None:
            action_mcp_metadata.setdefault("token", self.token)

        metadata = dict(raw_metadata)
        metadata["mcp"] = action_mcp_metadata

        register_action(
            app,
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            handler=func,
            transports=kwargs.get("transports") or self.transports,
            metadata=metadata,
            stream_output=bool(kwargs.get("stream_output", False)),
            stream_metadata=kwargs.get("stream_metadata"),
        )
        return func


class McpRouter:
    """Decorator-oriented MCP action registration for Muscles apps.

    Supported forms:

    * ``@app.mcp(route=..., name=..., ...)``
    * ``@app.mcp.server(name=..., route_prefix=..., ...)`` + ``@server.action(...)``
    """

    def __init__(self, *, route_prefix: str = "", transports: list[str] | None = None):
        self.route_prefix = _normalize_path(route_prefix)
        self.transports = list(transports or ["mcp"])

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return _BoundMcpRouter(instance, self)

    def __call__(self, **kwargs):
        raise AttributeError("Use @app_instance.mcp(...), where app_instance is a Muscles application instance")

    def action(self, **kwargs):
        raise AttributeError("Use @app_instance.mcp(...), where app_instance is a Muscles application instance")

    def server(self, **kwargs):
        raise AttributeError("Use @app_instance.mcp.server(...), where app_instance is a Muscles application instance")

    def _decorate_action(self, app, **kwargs):
        server = McpServer(
            route_prefix=self.route_prefix,
            transports=kwargs.get("transports") or self.transports,
            name="legacy",
            profile="default",
            metadata={"mcp": {"server": "legacy"}},
        )
        return server._decorate_action(app=app, **kwargs)

    def _build_server(self, app, **kwargs):
        server_route = _normalize_path(
            kwargs.get("route_prefix") or kwargs.get("route") or self.route_prefix or "/"
        )
        server = McpServer(
            route_prefix=_join_path(self.route_prefix, server_route),
            transports=kwargs.get("transports") or self.transports,
            name=_normalize_server_name(kwargs.get("name")) or "default",
            profile=_normalize_server_name(kwargs.get("profile")) or _normalize_server_name(kwargs.get("name")) or "default",
            token=kwargs.get("token"),
            metadata=kwargs.get("metadata"),
        )
        return _BoundMcpServer(app, server)


__all__ = ["McpRouter", "McpServer"]
