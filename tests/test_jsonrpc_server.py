import json

from muscles_mcp import (
    McpAccessDenied,
    McpInvalidParams,
    McpMethodNotFound,
    McpNotFound,
    McpResource,
    McpServer,
    McpTool,
    mcp_list_schema,
    mcp_object_schema,
    mcp_value_schema,
)


def _build_server(handler=None):
    return McpServer(
        name="assetforge-mcp",
        version="1.0.0",
        instructions="Use AssetForge tools.",
        tools=[
            McpTool(
                name="workspaces.list",
                description="List workspaces",
                input_schema={"type": "object", "properties": {}},
                output_schema=mcp_list_schema(),
                read_only=True,
            ),
            McpTool(
                name="documents.delete",
                description="Delete document",
                input_schema={"type": "object", "properties": {"uid": {"type": "string"}}},
                destructive=True,
            ),
        ],
        resources=[
            McpResource(
                uri="assetforge://catalog",
                name="catalog",
                description="AssetForge catalog",
            )
        ],
        call_tool=handler
        or (lambda name, arguments, context: [{"uid": "workspace-full-uid"}]),
        read_resource=lambda uri, arguments, context: {"uri": uri, "ok": True},
    )


def test_mcp_tool_descriptor_uses_protocol_schema_names_and_annotations():
    server = _build_server()

    response = server.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": [
                {
                    "name": "workspaces.list",
                    "description": "List workspaces",
                    "inputSchema": {"type": "object", "properties": {}},
                    "outputSchema": mcp_list_schema(),
                    "annotations": {
                        "title": "workspaces.list",
                        "readOnlyHint": True,
                        "destructiveHint": False,
                    },
                },
                {
                    "name": "documents.delete",
                    "description": "Delete document",
                    "inputSchema": {"type": "object", "properties": {"uid": {"type": "string"}}},
                    "outputSchema": mcp_object_schema(),
                    "annotations": {
                        "title": "documents.delete",
                        "readOnlyHint": False,
                        "destructiveHint": True,
                    },
                },
            ]
        },
    }


def test_mcp_initialize_returns_server_info_and_capabilities():
    server = _build_server()

    response = server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {"name": "assetforge-mcp", "version": "1.0.0"},
            "instructions": "Use AssetForge tools.",
        },
    }


def test_mcp_tool_descriptor_preserves_explicit_empty_output_schema():
    tool = McpTool(
        name="compat.empty_schema",
        description="Compatibility schema",
        input_schema={},
        output_schema={},
    )

    assert tool.to_descriptor()["outputSchema"] == {}


def test_mcp_tool_call_with_dict_keeps_structured_content_object():
    server = _build_server(handler=lambda name, arguments, context: {"uid": "doc-1"})

    response = server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {"name": "workspaces.list", "arguments": {}},
        }
    )

    result = response["result"]
    assert result["structuredContent"] == {"uid": "doc-1"}
    assert json.loads(result["content"][0]["text"]) == {"uid": "doc-1"}
    assert result["isError"] is False


def test_mcp_tool_call_with_list_wraps_items_and_count():
    server = _build_server(handler=lambda name, arguments, context: [{"uid": "w1"}, {"uid": "w2"}])

    response = server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "workspaces.list", "arguments": {}},
        }
    )

    assert response["result"]["structuredContent"] == {
        "items": [{"uid": "w1"}, {"uid": "w2"}],
        "count": 2,
    }


def test_mcp_tool_call_with_primitive_wraps_value():
    server = _build_server(handler=lambda name, arguments, context: True)

    response = server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "workspaces.list", "arguments": {}},
        }
    )

    assert response["result"]["structuredContent"] == {"value": True}


def test_mcp_jsonrpc_batch_requests_and_notifications():
    server = _build_server()

    response = server.handle_jsonrpc(
        [
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "resources/templates/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "prompts/list", "params": {}},
        ]
    )

    assert response == [
        {"jsonrpc": "2.0", "id": 1, "result": {}},
        {"jsonrpc": "2.0", "id": 2, "result": {"resourceTemplates": []}},
        {"jsonrpc": "2.0", "id": 3, "result": {"prompts": []}},
    ]


def test_mcp_jsonrpc_error_mapping():
    server = _build_server(handler=lambda name, arguments, context: (_ for _ in ()).throw(McpAccessDenied("Denied")))

    response = server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "workspaces.list", "arguments": {}},
        }
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": 4,
        "error": {"code": -32001, "message": "Denied"},
    }


def test_mcp_jsonrpc_maps_standard_error_codes():
    cases = [
        ({"not": "jsonrpc"}, -32600),
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "workspaces.list", "arguments": []},
            },
            -32602,
        ),
        ({"jsonrpc": "2.0", "id": 2, "method": "missing/method", "params": {}}, -32601),
    ]
    for message, code in cases:
        response = _build_server().handle_jsonrpc(message)
        assert response["error"]["code"] == code

    mapped_errors = [
        (McpInvalidParams("Bad params"), -32602),
        (McpMethodNotFound("Missing"), -32601),
        (McpNotFound("Gone"), -32004),
        (RuntimeError("Boom"), -32000),
    ]
    for error, code in mapped_errors:
        server = _build_server(handler=lambda name, arguments, context, error=error: (_ for _ in ()).throw(error))
        response = server.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "workspaces.list", "arguments": {}},
            }
        )
        assert response["error"]["code"] == code


def test_mcp_resources_list_and_read_use_text_contents():
    server = _build_server()

    resources = server.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}}
    )
    resource = server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/read",
            "params": {"uri": "assetforge://catalog", "arguments": {}},
        }
    )

    assert resources["result"]["resources"] == [
        {
            "uri": "assetforge://catalog",
            "name": "catalog",
            "description": "AssetForge catalog",
            "mimeType": "application/json",
        }
    ]
    assert resource["result"]["contents"][0]["uri"] == "assetforge://catalog"
    assert resource["result"]["contents"][0]["mimeType"] == "application/json"
    assert json.loads(resource["result"]["contents"][0]["text"]) == {
        "uri": "assetforge://catalog",
        "ok": True,
    }


def test_mcp_output_schema_helpers():
    assert mcp_object_schema() == {"type": "object", "additionalProperties": True}
    assert mcp_value_schema("boolean") == {
        "type": "object",
        "properties": {"value": {"type": "boolean"}},
        "required": ["value"],
        "additionalProperties": True,
    }
