from __future__ import annotations

import re
from typing import Any

from muscles.core import register_action

from .utils import build_model_json_schema


def _normalize_path(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    path = re.sub(r"/{2,}", "/", path)
    return f"/{path.strip('/')}" if path != "/" else "/"


def _join_path(base: str, path: str) -> str:
    if not base:
        return path
    base = base.rstrip("/")
    if path == "/":
        return base or "/"
    return f"{base}/{path.lstrip('/')}"


def _normalize_action_name(value: str) -> str:
    cleaned = re.sub(r"[{}]", "", value.strip())
    cleaned = cleaned.strip("/")
    cleaned = re.sub(r"[^0-9a-zA-Z_./-]", "", cleaned)
    cleaned = cleaned.replace("/", ".").replace("-", "_")
    return cleaned or "mcp_action"


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

    def __call__(self, **kwargs):
        return self._router._decorate_action(self._app, **kwargs)


class McpRouter:
    """Decorator-oriented MCP action registration for Muscles apps.

    Used as `@app.mcp(route="/bookings", name="bookings.create")`.
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
        return self.__call__(**kwargs)

    def _decorate_action(self, app, **kwargs):
        def decorator(func):
            return self._decorate_action_func(app, func, **kwargs)

        return decorator

    def _decorate_action_func(self, app, func, **kwargs):
        route = _normalize_path(kwargs.get("route") or kwargs.get("path") or "/")
        name = kwargs.get("name") or _normalize_action_name(route)
        description = kwargs.get("description") or (func.__doc__ or "").strip()
        input_schema = _coerce_model_schema(kwargs.get("input_schema"))
        output_schema = _coerce_model_schema(kwargs.get("output_schema"))
        metadata = dict(kwargs.get("metadata") or {})
        metadata.setdefault("mcp", {})
        metadata["mcp"].update(
            {
                "route": route,
                "full_route": _join_path(self.route_prefix, route),
                "name": name,
                "transport": "/".join(self.transports),
            }
        )
        register_action(
            app,
            name=kwargs.get("action_name", name),
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


__all__ = ["McpRouter"]
