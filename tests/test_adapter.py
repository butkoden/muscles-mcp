from muscles_mcp import McpAdapter


def test_mcp_builds_tools_and_resources_from_contract():
    contract = {
        "actions": [
            {
                "name": "bookings.create",
                "description": "Create booking",
                "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
            }
        ],
        "schemas": [{"name": "Booking", "type": "object", "properties": {"id": {"type": "integer"}}}],
    }
    adapter = McpAdapter(contract, action_handler=lambda name, args: {"name": name, "args": args})

    tools = adapter.list_tools()
    resources = adapter.list_resources()
    assert tools[0]["name"] == "bookings.create"
    assert resources[0]["uri"] == "muscles://schema/Booking"


def test_mcp_call_tool_routes_to_action_handler():
    called = {}

    def handler(name, args):
        called["name"] = name
        called["args"] = args
        return {"ok": True}

    adapter = McpAdapter({"actions": []}, handler)
    response = adapter.call_tool("bookings.create", {"title": "Call"})
    assert called == {"name": "bookings.create", "args": {"title": "Call"}}
    assert response == {"content": [{"type": "json", "json": {"ok": True}}]}
