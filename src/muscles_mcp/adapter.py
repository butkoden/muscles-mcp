from __future__ import annotations

from typing import Any

from .strategy import McpError, McpStrategy


class McpAdapter:
    """Compatibility facade for the MCP application strategy."""

    def __init__(self, app) -> None:
        self._app = app
        self._strategy = McpStrategy()

    @classmethod
    def from_application(cls, app):
        return cls(app)

    @property
    def _contract(self) -> dict[str, Any]:
        return self._strategy._contract(self._app)

    def list_tools(self) -> list[dict[str, Any]]:
        return self._strategy.list_tools(self._app)

    def list_resources(self) -> list[dict[str, Any]]:
        return self._strategy.list_resources()

    def read_resource(self, uri: str) -> dict[str, Any]:
        return self._strategy.read_resource(self._app, uri)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._strategy.execute(
            operation="call_tool",
            container=self._app,
            name=name,
            arguments=arguments or {},
        )

    @staticmethod
    def _map_core_error(exc: Exception) -> dict[str, Any] | None:
        return McpStrategy.map_core_error(exc)
