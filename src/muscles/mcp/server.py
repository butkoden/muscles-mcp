from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Protocol


MCP_PROTOCOL_VERSION = "2025-06-18"


def mcp_object_schema() -> dict[str, object]:
    return {"type": "object", "additionalProperties": True}


def mcp_list_schema(item_schema: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": item_schema or {"type": "object", "additionalProperties": True},
            },
            "count": {"type": "integer"},
        },
        "required": ["items", "count"],
        "additionalProperties": True,
    }


def mcp_value_schema(value_type: str = "string") -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"value": {"type": value_type}},
        "required": ["value"],
        "additionalProperties": True,
    }


def normalize_structured_content(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": value, "count": len(value)}
    return {"value": value}


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: dict[str, object]
    output_schema: dict[str, object] | None = None
    read_only: bool = False
    destructive: bool = False

    def to_descriptor(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema if self.output_schema is not None else mcp_object_schema(),
            "annotations": {
                "title": self.name,
                "readOnlyHint": bool(self.read_only),
                "destructiveHint": bool(self.destructive),
            },
        }


@dataclass(frozen=True)
class McpResource:
    uri: str
    name: str
    description: str
    mime_type: str = "application/json"

    def to_descriptor(self) -> dict[str, object]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass(frozen=True)
class McpRequestContext:
    request: Any = None
    request_id: str | int | None = None
    bearer_token: str | None = None
    client: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


class McpOAuthProvider(Protocol):
    def register_client(self, payload: dict[str, object], context: McpRequestContext) -> dict[str, object]:
        ...

    def issue_authorization_code(self, payload: dict[str, object], context: McpRequestContext) -> dict[str, object]:
        ...

    def exchange_code_for_token(self, payload: dict[str, object], context: McpRequestContext) -> dict[str, object]:
        ...


class McpJsonRpcException(Exception):
    jsonrpc_code = -32000

    def __init__(self, message: str, data: object | None = None):
        super().__init__(message)
        self.message = message
        self.data = data


class McpInvalidRequest(McpJsonRpcException):
    jsonrpc_code = -32600


class McpInvalidParams(McpJsonRpcException):
    jsonrpc_code = -32602


class McpMethodNotFound(McpJsonRpcException):
    jsonrpc_code = -32601


class McpAccessDenied(McpJsonRpcException):
    jsonrpc_code = -32001


class McpNotFound(McpJsonRpcException):
    jsonrpc_code = -32004


class McpInternalError(McpJsonRpcException):
    jsonrpc_code = -32000


@dataclass(frozen=True)
class McpJsonRpcError:
    code: int
    message: str
    data: object | None = None


ToolProvider = Iterable[McpTool] | Callable[[McpRequestContext], Iterable[McpTool]]
ResourceProvider = Iterable[McpResource] | Callable[[McpRequestContext], Iterable[McpResource]]
ToolHandler = Callable[[str, dict[str, object], McpRequestContext], object]
ResourceHandler = Callable[[str, dict[str, object], McpRequestContext], object]
ErrorMapper = Callable[[Exception], McpJsonRpcError | None]


@dataclass
class McpServer:
    name: str
    version: str
    instructions: str = ""
    tools: ToolProvider = field(default_factory=list)
    resources: ResourceProvider = field(default_factory=list)
    call_tool: ToolHandler | None = None
    read_resource: ResourceHandler | None = None
    error_mapper: ErrorMapper | None = None
    protocol_version: str = MCP_PROTOCOL_VERSION

    def handle_jsonrpc(
        self,
        message: dict[str, object] | list[object],
        context: McpRequestContext | dict[str, object] | None = None,
    ) -> dict[str, object] | list[dict[str, object]] | None:
        if isinstance(message, list):
            if not message:
                return self._rpc_error(None, -32600, "Invalid JSON-RPC batch request")
            responses = [
                response
                for response in (self._handle_single(item, context) for item in message)
                if response is not None
            ]
            return responses or None
        return self._handle_single(message, context)

    def _handle_single(
        self,
        message: object,
        context: McpRequestContext | dict[str, object] | None,
    ) -> dict[str, object] | None:
        if not isinstance(message, dict):
            return self._rpc_error(None, -32600, "Invalid JSON-RPC request")

        message_id = message.get("id")
        is_notification = False

        try:
            if message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
                raise McpInvalidRequest("Invalid JSON-RPC request")
            is_notification = "id" not in message
            params = message.get("params") or {}
            if not isinstance(params, dict):
                raise McpInvalidParams("params must be an object")

            result = self._dispatch(
                method=str(message["method"]),
                params=params,
                context=self._request_context(context, message_id),
            )
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": message_id, "result": result}
        except Exception as exc:
            if is_notification:
                return None
            mapped = self._map_error(exc)
            return self._rpc_error(message_id, mapped.code, mapped.message, mapped.data)

    def _dispatch(
        self,
        *,
        method: str,
        params: dict[str, object],
        context: McpRequestContext,
    ) -> dict[str, object]:
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [tool.to_descriptor() for tool in self._tools(context)]}
        if method == "tools/call":
            return self._call_tool(params, context)
        if method == "resources/list":
            return {"resources": [resource.to_descriptor() for resource in self._resources(context)]}
        if method == "resources/read":
            return self._read_resource(params, context)
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "prompts/list":
            return {"prompts": []}
        raise McpMethodNotFound(f"Method not found: {method}")

    def _initialize(self, params: dict[str, object]) -> dict[str, object]:
        protocol_version = params.get("protocolVersion") or self.protocol_version
        return {
            "protocolVersion": protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {"name": self.name, "version": self.version},
            "instructions": self.instructions,
        }

    def _call_tool(self, params: dict[str, object], context: McpRequestContext) -> dict[str, object]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name.strip():
            raise McpInvalidParams("Tool name is required")
        if not isinstance(arguments, dict):
            raise McpInvalidParams("Tool arguments must be an object")
        if self._find_tool(name, context) is None or self.call_tool is None:
            raise McpMethodNotFound(f"Tool not found: {name}")

        result = self.call_tool(name, arguments, context)
        structured_content = normalize_structured_content(result)
        return {
            "content": [{"type": "text", "text": _json_text(structured_content)}],
            "structuredContent": structured_content,
            "isError": False,
        }

    def _read_resource(self, params: dict[str, object], context: McpRequestContext) -> dict[str, object]:
        uri = params.get("uri")
        arguments = params.get("arguments", {})
        if not isinstance(uri, str) or not uri.strip():
            raise McpInvalidParams("Resource uri is required")
        if not isinstance(arguments, dict):
            raise McpInvalidParams("Resource arguments must be an object")
        resource = self._find_resource(uri, context)
        if resource is None or self.read_resource is None:
            raise McpMethodNotFound(f"Resource not found: {uri}")

        result = self.read_resource(uri, arguments, context)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": resource.mime_type,
                    "text": _json_text(result),
                }
            ]
        }

    def _tools(self, context: McpRequestContext) -> list[McpTool]:
        if callable(self.tools):
            return list(self.tools(context))
        return list(self.tools)

    def _resources(self, context: McpRequestContext) -> list[McpResource]:
        if callable(self.resources):
            return list(self.resources(context))
        return list(self.resources)

    def _find_tool(self, name: str, context: McpRequestContext) -> McpTool | None:
        for tool in self._tools(context):
            if tool.name == name:
                return tool
        return None

    def _find_resource(self, uri: str, context: McpRequestContext) -> McpResource | None:
        for resource in self._resources(context):
            if resource.uri == uri:
                return resource
        return None

    @staticmethod
    def _request_context(
        context: McpRequestContext | dict[str, object] | None,
        request_id: object,
    ) -> McpRequestContext:
        normalized_id = request_id if isinstance(request_id, (str, int)) else None
        if context is None:
            return McpRequestContext(request_id=normalized_id)
        if isinstance(context, McpRequestContext):
            return replace(context, request_id=normalized_id)
        return McpRequestContext(request_id=normalized_id, metadata=dict(context))

    def _map_error(self, exc: Exception) -> McpJsonRpcError:
        if self.error_mapper is not None:
            mapped = self.error_mapper(exc)
            if mapped is not None:
                return mapped

        if isinstance(exc, McpJsonRpcException):
            return McpJsonRpcError(exc.jsonrpc_code, exc.message, exc.data)

        class_name = exc.__class__.__name__
        message = str(exc)
        data = getattr(exc, "data", None)
        if class_name in {"McpOperationNotFound", "McpToolNotFound", "McpResourceNotFound", "OperationNotFound"}:
            return McpJsonRpcError(-32601, message, data)
        if class_name in {"McpValidationError", "InvalidParams", "ValidationError"} or isinstance(exc, ValueError):
            return McpJsonRpcError(-32602, message, data)
        if class_name in {"McpAccessDenied", "AccessDenied", "PermissionDenied"} or isinstance(exc, PermissionError):
            return McpJsonRpcError(-32001, message, data)
        if class_name in {"McpNotFound", "NotFound"} or isinstance(exc, KeyError):
            return McpJsonRpcError(-32004, message, data)
        return McpJsonRpcError(-32000, "Internal error", data)

    @staticmethod
    def _rpc_error(
        message_id: object,
        code: int,
        message: str,
        data: object | None = None,
    ) -> dict[str, object]:
        error: dict[str, object] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": message_id, "error": error}


@dataclass(frozen=True)
class McpHttpResponse:
    body: object = None
    status: int = 200
    headers: list[tuple[str, str]] = field(default_factory=list)
    content_type: str = "application/json; charset=utf-8"


def oauth_protected_resource_metadata(
    base_url: str,
    *,
    resource_path: str = "/mcp",
    scope: str = "mcp",
    resource_documentation_path: str = "/app",
) -> dict[str, object]:
    base = _clean_base_url(base_url)
    return {
        "resource": f"{base}{_clean_path(resource_path)}",
        "authorization_servers": [base],
        "scopes_supported": [scope],
        "resource_documentation": f"{base}{_clean_path(resource_documentation_path)}",
        "bearer_methods_supported": ["header"],
    }


def oauth_authorization_server_metadata(
    base_url: str,
    *,
    scope: str = "mcp",
    authorization_path: str = "/oauth/authorize",
    token_path: str = "/oauth/token",
    registration_path: str = "/oauth/register",
    resource_documentation_path: str = "/app",
) -> dict[str, object]:
    base = _clean_base_url(base_url)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}{_clean_path(authorization_path)}",
        "token_endpoint": f"{base}{_clean_path(token_path)}",
        "registration_endpoint": f"{base}{_clean_path(registration_path)}",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "scopes_supported": [scope],
        "resource_documentation": f"{base}{_clean_path(resource_documentation_path)}",
    }


def register_mcp_routes(
    routes: Any,
    *,
    path: str = "/mcp",
    server: McpServer,
    oauth: McpOAuthProvider | None = None,
    scope: str = "mcp",
    base_url: Callable[[Any], str] | None = None,
    response_factory: Callable[..., Any] | None = None,
) -> None:
    mcp_path = _clean_path(path)
    resolve_base_url = base_url or _base_url_from_request

    def response(body: object = None, *, status: int = 200, headers: list[tuple[str, str]] | None = None):
        headers = headers or []
        if response_factory is not None:
            return response_factory(body=body, status=status, headers=headers, content_type="application/json; charset=utf-8")
        return McpHttpResponse(body=body, status=status, headers=headers)

    def protected_metadata(request):
        return response(
            oauth_protected_resource_metadata(
                resolve_base_url(request),
                resource_path=mcp_path,
                scope=scope,
            )
        )

    def authorization_metadata(request):
        return response(oauth_authorization_server_metadata(resolve_base_url(request), scope=scope))

    @routes.init("/.well-known/oauth-protected-resource", method="GET")
    def get_oauth_protected_resource_metadata(request):
        return protected_metadata(request)

    @routes.init("/.well-known/oauth-protected-resource/mcp", method="GET")
    def get_mcp_oauth_protected_resource_metadata(request):
        return protected_metadata(request)

    @routes.init("/.well-known/oauth-authorization-server", method="GET")
    def get_oauth_authorization_server_metadata(request):
        return authorization_metadata(request)

    @routes.init("/.well-known/oauth-authorization-server/mcp", method="GET")
    def get_mcp_oauth_authorization_server_metadata(request):
        return authorization_metadata(request)

    @routes.init("/oauth/register", method="POST")
    def register_oauth_client(request):
        if oauth is None:
            return response({"detail": "OAuth provider is not configured"}, status=501)
        return response(oauth.register_client(_request_json(request), McpRequestContext(request=request)), status=201)

    @routes.init("/oauth/authorize", method="GET")
    def get_oauth_authorization(request):
        if oauth is None:
            return response({"detail": "OAuth provider is not configured"}, status=501)
        return response(oauth.issue_authorization_code(_request_query(request), McpRequestContext(request=request)))

    @routes.init("/oauth/authorize", method="POST")
    def authorize_oauth_client(request):
        if oauth is None:
            return response({"detail": "OAuth provider is not configured"}, status=501)
        return response(oauth.issue_authorization_code(_request_json(request), McpRequestContext(request=request)))

    @routes.init("/oauth/token", method="POST")
    def issue_oauth_token(request):
        if oauth is None:
            return response({"detail": "OAuth provider is not configured"}, status=501)
        return response(oauth.exchange_code_for_token(_request_json(request), McpRequestContext(request=request)))

    @routes.init(mcp_path, method="GET")
    def get_mcp_transport(request):
        return response(
            {"detail": "MCP Streamable HTTP uses POST on this server"},
            status=405,
            headers=[("Allow", "POST")],
        )

    @routes.init(mcp_path, method="POST")
    def post_mcp_transport(request):
        result = server.handle_jsonrpc(_request_json(request), McpRequestContext(request=request))
        if result is None:
            return response("", status=202)
        return response(result)


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _clean_base_url(base_url: str) -> str:
    return str(base_url).strip().rstrip("/")


def _clean_path(path: str) -> str:
    return f"/{str(path).strip().lstrip('/')}"


def _request_json(request: Any) -> dict[str, object] | list[object]:
    if request is None:
        return {}
    if isinstance(request, (dict, list)):
        return request
    if hasattr(request, "json"):
        value = request.json() if callable(request.json) else request.json
        if isinstance(value, (dict, list)):
            return value
    body = getattr(request, "body", None)
    if isinstance(body, (dict, list)):
        return body
    if isinstance(body, bytes):
        return json.loads(body.decode("utf-8")) if body else {}
    if isinstance(body, str):
        return json.loads(body) if body else {}
    return {}


def _request_query(request: Any) -> dict[str, object]:
    if request is None:
        return {}
    query = getattr(request, "query", None)
    if isinstance(query, dict):
        return query
    query_params = getattr(request, "query_params", None)
    if isinstance(query_params, dict):
        return query_params
    return {}


def _base_url_from_request(request: Any) -> str:
    if request is None:
        return "http://localhost"
    headers = getattr(request, "headers", {}) or {}
    if not isinstance(headers, dict):
        headers = {}
    proto = headers.get("x-forwarded-proto") or getattr(request, "scheme", None) or "http"
    host = headers.get("x-forwarded-host") or headers.get("host") or getattr(request, "netloc", None) or "localhost"
    return f"{str(proto).split(',', 1)[0].strip()}://{str(host).split(',', 1)[0].strip()}".rstrip("/")


__all__ = [
    "MCP_PROTOCOL_VERSION",
    "McpAccessDenied",
    "McpHttpResponse",
    "McpInternalError",
    "McpInvalidParams",
    "McpInvalidRequest",
    "McpJsonRpcError",
    "McpJsonRpcException",
    "McpMethodNotFound",
    "McpNotFound",
    "McpOAuthProvider",
    "McpRequestContext",
    "McpResource",
    "McpServer",
    "McpTool",
    "mcp_list_schema",
    "mcp_object_schema",
    "mcp_value_schema",
    "normalize_structured_content",
    "oauth_authorization_server_metadata",
    "oauth_protected_resource_metadata",
    "register_mcp_routes",
]
