from __future__ import annotations

from typing import Any, Callable


class McpAdapter:
    """Builds MCP-exposed tools/resources from Muscles inspect contract."""

    def __init__(self, inspect_contract: dict[str, Any], action_handler: Callable[[str, dict[str, Any]], Any]) -> None:
        self._contract = inspect_contract
        self._action_handler = action_handler

    @classmethod
    def from_application(cls, app, action_handler: Callable[[str, dict[str, Any]], Any] | None = None):
        from muscles.core import inspect_application

        contract = inspect_application(app)
        handler = action_handler or (lambda name, args: app.context.execute(name, **args))
        return cls(contract, handler)

    def list_tools(self) -> list[dict[str, Any]]:
        actions = self._contract.get("actions", [])
        tools: list[dict[str, Any]] = []
        for action in actions:
            name = action.get("name") or action.get("action")
            if not name:
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
            schema = self._tool_input_schema(name)
            self._validate_arguments(schema, payload)
            result = self._action_handler(name, payload)
            return {"content": [{"type": "json", "json": result}]}
        except PermissionError as exc:
            return {"isError": True, "error": {"code": "permission_denied", "message": str(exc)}}
        except McpError as exc:
            return {"isError": True, "error": {"code": exc.code, "message": exc.message, "data": exc.data}}

    def _tool_input_schema(self, tool_name: str) -> dict[str, Any]:
        for tool in self.list_tools():
            if tool["name"] == tool_name:
                return tool.get("input_schema") or {"type": "object", "properties": {}}
        raise McpError(code="not_found", message=f"Unknown tool: {tool_name}")

    @staticmethod
    def _validate_arguments(schema: dict[str, Any], payload: dict[str, Any]) -> None:
        if schema.get("type") not in (None, "object"):
            raise McpError(code="invalid_schema", message="Only object input_schema is supported in stage #1")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in payload:
                raise McpError(code="invalid_params", message=f"Missing required argument: {key}")
        for key, value in payload.items():
            spec = properties.get(key)
            if not spec:
                continue
            expected = spec.get("type")
            if expected == "string" and not isinstance(value, str):
                raise McpError(code="invalid_params", message=f"Argument {key} must be string")
            if expected == "integer" and not isinstance(value, int):
                raise McpError(code="invalid_params", message=f"Argument {key} must be integer")


class McpError(Exception):
    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
