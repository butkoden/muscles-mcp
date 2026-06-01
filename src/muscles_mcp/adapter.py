from __future__ import annotations

from typing import Any, Callable


class McpAdapter:
    """Builds MCP-exposed tools/resources from Muscles inspect contract."""

    def __init__(self, inspect_contract: dict[str, Any], action_handler: Callable[[str, dict[str, Any]], Any]) -> None:
        self._contract = inspect_contract
        self._action_handler = action_handler

    def list_tools(self) -> list[dict[str, Any]]:
        actions = self._contract.get("actions", [])
        tools: list[dict[str, Any]] = []
        for action in actions:
            name = action.get("name")
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
        schemas = self._contract.get("schemas", [])
        resources: list[dict[str, Any]] = []
        for schema in schemas:
            name = schema.get("name")
            if not name:
                continue
            resources.append({"uri": f"muscles://schema/{name}", "name": name, "schema": schema})
        return resources

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = arguments or {}
        result = self._action_handler(name, payload)
        return {"content": [{"type": "json", "json": result}]}
