from __future__ import annotations

from typing import Any


class McpAdapter:
    """Projects a Muscles application contract into MCP tools/resources."""

    def __init__(self, app) -> None:
        self._app = app

    @classmethod
    def from_application(cls, app):
        return cls(app)

    @property
    def _contract(self) -> dict[str, Any]:
        from muscles.core import inspect_application

        return inspect_application(self._app)

    def list_tools(self) -> list[dict[str, Any]]:
        actions = self._contract.get("actions", [])
        tools: list[dict[str, Any]] = []
        for action in actions:
            name = action.get("name") or action.get("action")
            if not name:
                continue
            transports = action.get("transports") or []
            if transports and "mcp" not in transports:
                continue
            tools.append(
                {
                    "name": name,
                    "description": action.get("description", ""),
                    "input_schema": action.get("input_schema", {"type": "object", "properties": {}}),
                }
            )
        return tools

    def list_resources(self) -> list[dict[str, Any]]:
        return [
            {"uri": "muscles://app/inspect", "name": "inspect"},
            {"uri": "muscles://app/actions", "name": "actions"},
            {"uri": "muscles://app/routes", "name": "routes"},
            {"uri": "muscles://app/schemas", "name": "schemas"},
            {"uri": "muscles://app/rules", "name": "rules"},
        ]

    def read_resource(self, uri: str) -> dict[str, Any]:
        mapping = {
            "muscles://app/inspect": self._contract,
            "muscles://app/actions": self._contract.get("actions", []),
            "muscles://app/routes": self._contract.get("routes", []),
            "muscles://app/schemas": self._contract.get("schemas", []),
            "muscles://app/rules": self._contract.get("rules", []),
        }
        if uri not in mapping:
            raise McpError(code="not_found", message=f"Unknown resource: {uri}")
        return {"contents": [{"uri": uri, "mimeType": "application/json", "json": mapping[uri]}]}

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = arguments or {}
        try:
            from muscles.core import ActionDispatcher

            result = ActionDispatcher(self._app).execute(name, payload, transport="mcp")
            return {"content": [{"type": "json", "json": result.value}]}
        except Exception as exc:
            mapped = self._map_core_error(exc)
            if mapped is not None:
                return {"isError": True, "error": mapped}
            return {"isError": True, "error": {"code": "internal_error", "message": "Internal error", "data": None}}

    @staticmethod
    def _map_core_error(exc: Exception) -> dict[str, Any] | None:
        try:
            from muscles.core import (
                ActionExecutionError,
                ActionNotFound,
                ActionPermissionDenied,
                ActionValidationError,
            )
        except Exception:
            return None

        if isinstance(exc, ActionNotFound):
            return {"code": "not_found", "message": exc.message, "data": exc.data}
        if isinstance(exc, ActionValidationError):
            return {"code": "invalid_params", "message": exc.message, "data": exc.data}
        if isinstance(exc, ActionPermissionDenied):
            return {"code": "permission_denied", "message": exc.message, "data": exc.data}
        if isinstance(exc, ActionExecutionError):
            return {"code": "execution_error", "message": exc.message, "data": exc.data}
        return None

class McpError(Exception):
    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
