from __future__ import annotations

from typing import Any

from muscles.core import BaseStrategy

from .schema.mcp import (
    McpResourceDescriptor,
    McpResourceReadResult,
    McpToolCallRequest,
    McpToolCallResult,
    McpToolDescriptor,
)


RESOURCE_MAP = {
    "muscles://app/inspect": "inspect",
    "muscles://app/actions": "actions",
    "muscles://app/routes": "routes",
    "muscles://app/schemas": "schemas",
    "muscles://app/rules": "rules",
}


class McpStrategy(BaseStrategy):
    """MCP protocol strategy bound to a Muscles application Context."""

    def execute(self, *args, operation: str | None = None, container=None, **kwargs):
        app = self._resolve_application(kwargs.pop("app", None) or container)
        if app is None:
            raise McpError(code="application_required", message="MCP strategy requires a Muscles application")

        operation = operation or (args[0] if args else None)
        if operation == "list_tools":
            return self.list_tools(app)
        if operation == "list_resources":
            return self.list_resources()
        if operation == "read_resource":
            return self.read_resource(app, kwargs["uri"])
        if operation == "call_tool":
            request = McpToolCallRequest.from_payload(
                {
                    "name": kwargs.get("name"),
                    "arguments": kwargs.get("arguments") or {},
                }
            )
            return self.call_tool(app, request)
        raise McpError(code="unknown_operation", message=f"Unknown MCP operation: {operation}")

    def list_tools(self, app) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for action in self._contract(app).get("actions", []):
            name = action.get("name") or action.get("action")
            if not name:
                continue
            transports = action.get("transports") or []
            if transports and "mcp" not in transports:
                continue
            tool = McpToolDescriptor.from_action_contract({**action, "name": name})
            tools.append(tool.to_payload())
        return tools

    def list_resources(self) -> list[dict[str, Any]]:
        return [
            McpResourceDescriptor(uri=uri, name=name).to_payload()
            for uri, name in RESOURCE_MAP.items()
        ]

    def read_resource(self, app, uri: str) -> dict[str, Any]:
        contract = self._contract(app)
        mapping = {
            "muscles://app/inspect": contract,
            "muscles://app/actions": contract.get("actions", []),
            "muscles://app/routes": contract.get("routes", []),
            "muscles://app/schemas": contract.get("schemas", []),
            "muscles://app/rules": contract.get("rules", []),
        }
        if uri not in mapping:
            raise McpError(code="not_found", message=f"Unknown resource: {uri}")
        return McpResourceReadResult.from_json(uri, mapping[uri]).to_payload()

    def call_tool(self, app, request: McpToolCallRequest) -> dict[str, Any]:
        try:
            from muscles.core import ActionDispatcher

            payload = request.to_payload()
            result = ActionDispatcher(app).execute(payload["name"], payload["arguments"], transport="mcp")
            return McpToolCallResult.success(result.value).to_payload()
        except Exception as exc:
            mapped = self.map_core_error(exc)
            if mapped is not None:
                return McpToolCallResult.failure(**mapped).to_payload()
            return McpToolCallResult.failure(
                code="internal_error",
                message="Internal error",
                data=None,
            ).to_payload()

    @staticmethod
    def _resolve_application(app):
        if isinstance(app, type):
            return app()
        return app

    @staticmethod
    def _contract(app) -> dict[str, Any]:
        from muscles.core import inspect_application

        return inspect_application(app)

    @staticmethod
    def map_core_error(exc: Exception) -> dict[str, Any] | None:
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
