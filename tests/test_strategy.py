from muscles.core import ApplicationMeta, BaseStrategy, Context, register_action

from muscles_mcp import McpAdapter, McpStrategy


class _EchoStrategy(BaseStrategy):
    def execute(self, *args, **kwargs):
        return kwargs


BOOKING_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "guest_count": {"type": "integer"},
    },
    "required": ["title"],
}


def _build_mcp_app():
    class _McpApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)

    app = _McpApp()
    calls = []

    def create_booking(payload, context):
        calls.append((context.action.name, payload, context.transport))
        return {
            "id": len(calls),
            "title": payload["title"],
            "guest_count": payload.get("guest_count", 1),
        }

    register_action(
        app,
        name="bookings.create",
        description="Create booking",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["mcp"],
        handler=create_booking,
    )
    return app, calls


def test_mcp_strategy_lists_tools_from_application_context():
    app, _ = _build_mcp_app()

    tools = app.context.execute(operation="list_tools")

    assert tools == [
        {
            "name": "bookings.create",
            "description": "Create booking",
            "input_schema": BOOKING_INPUT_SCHEMA,
        }
    ]


def test_mcp_strategy_calls_tool_through_application_context():
    app, calls = _build_mcp_app()

    response = app.context.execute(
        operation="call_tool",
        name="bookings.create",
        arguments={"title": "Context call", "guest_count": 3},
    )

    assert calls == [("bookings.create", {"title": "Context call", "guest_count": 3}, "mcp")]
    assert response == {
        "content": [
            {
                "type": "json",
                "json": {"id": 1, "title": "Context call", "guest_count": 3},
            }
        ]
    }


def test_mcp_adapter_is_facade_over_strategy_projection():
    app, calls = _build_mcp_app()

    adapter = McpAdapter.from_application(app)

    assert adapter.list_tools() == app.context.execute(operation="list_tools")
    response = adapter.call_tool("bookings.create", {"title": "Facade"})

    assert calls == [("bookings.create", {"title": "Facade"}, "mcp")]
    assert response["content"][0]["json"]["title"] == "Facade"


def test_mcp_strategy_state_is_scoped_to_container_application():
    app_a, _ = _build_mcp_app()

    class _OtherMcpApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)

    app_b = _OtherMcpApp()
    register_action(
        app_b,
        name="tasks.create",
        input_schema={"type": "object", "properties": {}},
        transports=["mcp"],
        handler=lambda payload, context: {"ok": True},
    )

    tools_a = app_a.context.execute(operation="list_tools")
    tools_b = app_b.context.execute(operation="list_tools")

    assert [tool["name"] for tool in tools_a] == ["bookings.create"]
    assert [tool["name"] for tool in tools_b] == ["tasks.create"]
