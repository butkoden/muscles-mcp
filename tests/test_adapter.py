from muscles.core import (
    ActionPermissionDenied,
    ApplicationMeta,
    BaseStrategy,
    Context,
    register_action,
)

from muscles_mcp import McpAdapter


class _EchoStrategy(BaseStrategy):
    def execute(self, *args, **kwargs):
        return kwargs


class _BookingApp(metaclass=ApplicationMeta):
    context = Context(_EchoStrategy)


BOOKING_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "guest_count": {"type": "integer"},
    },
    "required": ["title"],
}


def _build_app(handler=None, rules=None):
    class _App(metaclass=ApplicationMeta):
        context = Context(_EchoStrategy)

    app = _App()
    calls = []

    def default_handler(payload, context):
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
        output_schema={"type": "object", "properties": {"id": {"type": "integer"}}},
        rules=rules or ["bookings.public_create"],
        transports=["http", "cli", "mcp"],
        handler=handler or default_handler,
    )
    return app, calls


def test_mcp_builds_tools_and_resources_from_core_contract():
    app, _ = _build_app()
    adapter = McpAdapter.from_application(app)

    tools = adapter.list_tools()
    resources = adapter.list_resources()

    assert tools == [
        {
            "name": "bookings.create",
            "description": "Create booking",
            "input_schema": BOOKING_INPUT_SCHEMA,
        }
    ]
    assert {r["uri"] for r in resources} == {
        "muscles://app/inspect",
        "muscles://app/actions",
        "muscles://app/routes",
        "muscles://app/schemas",
        "muscles://app/rules",
    }
    inspect_resource = adapter.read_resource("muscles://app/inspect")
    assert inspect_resource["contents"][0]["json"]["actions"][0]["name"] == "bookings.create"


def test_mcp_call_tool_uses_core_dispatcher_once():
    app, calls = _build_app()
    adapter = McpAdapter.from_application(app)

    response = adapter.call_tool("bookings.create", {"title": "Call", "guest_count": 2})

    assert calls == [("bookings.create", {"title": "Call", "guest_count": 2}, "mcp")]
    assert response == {
        "content": [
            {
                "type": "json",
                "json": {"id": 1, "title": "Call", "guest_count": 2},
            }
        ]
    }


def test_mcp_invalid_payload_returns_core_validation_error():
    app, _ = _build_app()
    adapter = McpAdapter.from_application(app)

    response = adapter.call_tool("bookings.create", {"guest_count": 2})

    assert response["isError"] is True
    assert response["error"]["code"] == "invalid_params"
    assert "title" in response["error"]["message"]


def test_mcp_permission_denial_returns_core_permission_error():
    def deny(payload, context):
        raise ActionPermissionDenied(context.action.name, "Denied by core rules")

    app, _ = _build_app(handler=deny)
    adapter = McpAdapter.from_application(app)

    response = adapter.call_tool("bookings.create", {"title": "Call"})

    assert response["isError"] is True
    assert response["error"]["code"] == "permission_denied"
    assert response["error"]["message"] == "Denied by core rules"


def test_mcp_unknown_tool_returns_core_not_found_error():
    app, _ = _build_app()
    adapter = McpAdapter.from_application(app)

    response = adapter.call_tool("bookings.missing", {})

    assert response["isError"] is True
    assert response["error"]["code"] == "not_found"


def test_mcp_state_is_scoped_to_application_instance():
    app_a, _ = _build_app()

    class _OtherApp(metaclass=ApplicationMeta):
        context = Context(_EchoStrategy)

    app_b = _OtherApp()
    register_action(
        app_b,
        name="tasks.create",
        input_schema={"type": "object", "properties": {}},
        handler=lambda payload, context: {"ok": True},
    )

    tools_a = McpAdapter.from_application(app_a).list_tools()
    tools_b = McpAdapter.from_application(app_b).list_tools()

    assert [tool["name"] for tool in tools_a] == ["bookings.create"]
    assert [tool["name"] for tool in tools_b] == ["tasks.create"]
