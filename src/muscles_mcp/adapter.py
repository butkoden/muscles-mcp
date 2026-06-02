from __future__ import annotations

from typing import Any

from muscles.core import Context
from .strategy import McpError, McpStrategy


def _iter_app_contexts(app) -> list[tuple[str, Context]]:
    contexts: list[tuple[str, Context]] = []
    seen: set[str] = set()

    if app is None:
        return contexts

    for cls in app.__class__.mro():
        for name, value in vars(cls).items():
            if not isinstance(value, Context) or name in seen:
                continue
            seen.add(name)
            contexts.append((name, value))

    for name, value in vars(app).items():
        if not isinstance(value, Context) or name in seen:
            continue
        seen.add(name)
        contexts.append((name, value))

    return contexts


def _context_transport_name(context: Context | None) -> str | None:
    if context is None:
        return None
    return getattr(context, "_name", None)


def _matches_transport(context_transport: Any, transport: Any, _seen: set[int] | None = None) -> bool:

    if transport is context_transport:
        return True

    if isinstance(transport, Context):
        transport_name = _context_transport_name(transport)
        if transport_name is None:
            return False
        return _matches_transport(context_transport, transport_name, _seen=_seen)

    if not isinstance(context_transport, Context):
        return context_transport == transport

    context_transport_name = _context_transport_name(context_transport)
    if context_transport_name and context_transport_name == transport:
        return True

    if _seen is None:
        _seen = set()
    context_id = id(context_transport)
    if context_id in _seen:
        return False
    _seen.add(context_id)

    return _matches_transport(context_transport.transport, transport, _seen=_seen)


def resolve_mcp_context(
    app,
    *,
    context: str | Context | None = None,
    transport: Any = None,
    default: str | None = None,
) -> Context | None:
    """Resolve app context by explicit name, then transport, then fallback.

    Explicit context by name has highest priority. When transport is provided and a
    matching context is found it is returned. For backward compatibility, when no
    context is found by name/transport we can fallback to the provided default
    context name.
    """

    if app is None:
        return None

    if context is not None:
        if isinstance(context, Context):
            return context
        if isinstance(context, str):
            value = getattr(app, context, None)
            if isinstance(value, Context):
                return value
            raise ValueError(f"Application has no context '{context}'")
        raise TypeError("Context selector must be a context name (str) or Context instance")

    if transport is not None and isinstance(transport, str):
        named_context = getattr(app, transport, None)
        if isinstance(named_context, Context):
            return named_context

    transport_targets = []
    if transport is not None:
        for name, value in _iter_app_contexts(app):
            if _matches_transport(value.transport, transport):
                transport_targets.append((name, value))

    if transport is None:
        if default is not None:
            fallback = getattr(app, default, None)
            if isinstance(fallback, Context):
                return fallback
        return None

    if len(transport_targets) == 1:
        return transport_targets[0][1]
    if len(transport_targets) > 1:
        names = ", ".join(name for name, _ in transport_targets)
        raise ValueError(
            f"Context transport selector '{transport}' is ambiguous ({names}). "
            "Pass explicit context name or Context instance as context=..."
        )

    if default is not None:
        fallback = getattr(app, default, None)
        if isinstance(fallback, Context):
            return fallback

    return None


class McpAdapter:
    """Compatibility facade for the MCP application strategy."""

    def __init__(self, app, context: str | Context | None = None, transport: str | None = "mcp") -> None:
        self._app = app
        self._strategy = McpStrategy()
        self._context_selector = context
        self._transport = transport

    @classmethod
    def from_application(cls, app, context: str | Context | None = None):
        return cls(app, context=context)

    @property
    def context(self) -> Context | None:
        return self._resolve_context()

    @property
    def _contract(self) -> dict[str, Any]:
        return self._strategy._contract(self._app)

    def _resolve_context(self) -> Context | None:
        return resolve_mcp_context(
            self._app,
            context=self._context_selector,
            transport=self._transport,
            default=None,
        )

    def _execute(self, operation: str, **kwargs) -> dict[str, Any]:
        context = self._resolve_context()
        request = kwargs.get("request") if "request" in kwargs else None
        if context is not None:
            return context.execute(
                operation=operation,
                container=self._app,
                request=request,
                **{k: v for k, v in kwargs.items() if k != "request"},
            )

        return self._strategy.execute(
            container=self._app,
            operation=operation,
            request=request,
            **{k: v for k, v in kwargs.items() if k != "request"},
        )

    def execute(self, request: dict | None = None, operation: str | None = None, **kwargs) -> dict[str, Any]:
        return self._execute(operation=operation or (request or {}).get("operation") if request else operation, request=request, **kwargs)

    def list_tools(self) -> list[dict[str, Any]]:
        return self._execute("list_tools")

    def list_resources(self) -> list[dict[str, Any]]:
        return self._execute("list_resources")

    def read_resource(self, uri: str) -> dict[str, Any]:
        return self._execute("read_resource", uri=uri)

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        server: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            operation="call_tool",
            name=name,
            arguments=arguments or {},
            server=server,
            token=token,
        )

    @staticmethod
    def _map_core_error(exc: Exception) -> dict[str, Any] | None:
        return McpStrategy.map_core_error(exc)
