from muscles_mcp import McpAdapter


def test_mcp_builds_tools_and_resources_from_contract():
    contract = {
        "actions": [
            {
                "name": "bookings.create",
                "description": "Create booking",
                "input_schema": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                },
            }
        ],
        "schemas": [{"name": "Booking", "type": "object", "properties": {"id": {"type": "integer"}}}],
        "routes": [{"path": "/bookings"}],
        "rules": [{"name": "auth.required"}],
    }
    adapter = McpAdapter(contract, action_handler=lambda name, args: {"name": name, "args": args})

    tools = adapter.list_tools()
    resources = adapter.list_resources()
    assert tools[0]["name"] == "bookings.create"
    assert resources[0]["uri"] == "muscles://app/inspect"
    assert {r["uri"] for r in resources} == {
        "muscles://app/inspect",
        "muscles://app/actions",
        "muscles://app/routes",
        "muscles://app/schemas",
        "muscles://app/rules",
    }
    inspect_resource = adapter.read_resource("muscles://app/inspect")
    assert inspect_resource["contents"][0]["json"]["routes"][0]["path"] == "/bookings"


def test_mcp_call_tool_routes_to_action_handler():
    called = {}

    def handler(name, args):
        called["name"] = name
        called["args"] = args
        return {"ok": True}

    adapter = McpAdapter({"actions": [{"name": "bookings.create", "input_schema": {"type": "object", "properties": {}}}]}, handler)
    response = adapter.call_tool("bookings.create", {"title": "Call"})
    assert called == {"name": "bookings.create", "args": {"title": "Call"}}
    assert response == {"content": [{"type": "json", "json": {"ok": True}}]}


def test_mcp_tool_validation_uses_input_schema():
    contract = {
        "actions": [
            {
                "name": "bookings.create",
                "input_schema": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                },
            }
        ]
    }
    adapter = McpAdapter(contract, action_handler=lambda name, args: {"ok": True})
    error_missing = adapter.call_tool("bookings.create", {})
    assert error_missing["isError"] is True
    assert error_missing["error"]["code"] == "invalid_params"

    error_type = adapter.call_tool("bookings.create", {"title": 123})
    assert error_type["isError"] is True
    assert error_type["error"]["code"] == "invalid_params"


def test_mcp_permission_denial_is_structured_error():
    contract = {"actions": [{"name": "bookings.create", "input_schema": {"type": "object", "properties": {}}}]}

    def denied(name, args):
        raise PermissionError("Denied by rules")

    adapter = McpAdapter(contract, action_handler=denied)
    response = adapter.call_tool("bookings.create", {})
    assert response["isError"] is True
    assert response["error"]["code"] == "permission_denied"
