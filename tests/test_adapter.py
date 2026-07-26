from muscles.core import (
    ActionPermissionDenied,
    ApplicationMeta,
    BaseStrategy,
    Context,
)

from muscles_mcp import McpAdapter
from muscles_mcp.strategy import McpStrategy
from muscles_mcp.adapter import resolve_mcp_context


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


def add_action(app, **options):
    handler = options.pop("handler")
    app.action(**options)(handler)


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

    add_action(
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
        "muscles://app/capabilities",
        "muscles://app/architecture",
        "muscles://app/routes",
        "muscles://app/schemas",
        "muscles://app/rules",
    }
    inspect_resource = adapter.read_resource("muscles://app/inspect")
    assert inspect_resource["contents"][0]["json"]["actions"][0]["name"] == "bookings.create"


def test_mcp_lists_only_actions_open_to_mcp_transport():
    class _App(metaclass=ApplicationMeta):
        context = Context(_EchoStrategy)

    app = _App()
    add_action(
        app,
        name="bookings.http_only",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["http"],
        handler=lambda payload, context: {"transport": context.transport},
    )
    add_action(
        app,
        name="bookings.open",
        input_schema=BOOKING_INPUT_SCHEMA,
        handler=lambda payload, context: {"transport": context.transport},
    )
    add_action(
        app,
        name="bookings.mcp",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["mcp"],
        handler=lambda payload, context: {"transport": context.transport},
    )

    tools = McpAdapter.from_application(app).list_tools()

    assert [tool["name"] for tool in tools] == ["bookings.open", "bookings.mcp"]


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


def test_mcp_call_tool_denies_action_not_open_to_mcp_transport():
    class _App(metaclass=ApplicationMeta):
        context = Context(_EchoStrategy)

    app = _App()
    add_action(
        app,
        name="bookings.http_only",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["http"],
        handler=lambda payload, context: {"transport": context.transport},
    )
    adapter = McpAdapter.from_application(app)

    response = adapter.call_tool("bookings.http_only", {"title": "Call"})

    assert response["isError"] is True
    assert response["error"]["code"] == "permission_denied"


def test_mcp_async_handler_returns_execution_error():
    class _App(metaclass=ApplicationMeta):
        context = Context(_EchoStrategy)

    app = _App()

    async def create_booking(payload, context):
        return {"title": payload["title"]}

    add_action(
        app,
        name="bookings.async",
        input_schema=BOOKING_INPUT_SCHEMA,
        handler=create_booking,
    )
    adapter = McpAdapter.from_application(app)

    response = adapter.call_tool("bookings.async", {"title": "Call"})

    assert response["isError"] is True
    assert response["error"]["code"] == "execution_error"


def test_mcp_state_is_scoped_to_application_instance():
    app_a, _ = _build_app()

    class _OtherApp(metaclass=ApplicationMeta):
        context = Context(_EchoStrategy)

    app_b = _OtherApp()
    add_action(
        app_b,
        name="tasks.create",
        input_schema={"type": "object", "properties": {}},
        handler=lambda payload, context: {"ok": True},
    )

    tools_a = McpAdapter.from_application(app_a).list_tools()
    tools_b = McpAdapter.from_application(app_b).list_tools()

    assert [tool["name"] for tool in tools_a] == ["bookings.create"]
    assert [tool["name"] for tool in tools_b] == ["tasks.create"]


def test_resolve_mcp_context_matches_context_reference():
    public = Context(_EchoStrategy)

    class _App(metaclass=ApplicationMeta):
        asgi_public = public
        mcp_private = Context(_EchoStrategy, transport=public)

    app = _App()

    assert resolve_mcp_context(app, transport=public) is app.mcp_private
    assert resolve_mcp_context(app, context="mcp_private") is app.mcp_private


def test_resolve_mcp_context_matches_named_transport():
    class _App(metaclass=ApplicationMeta):
        asgi_public = Context(_EchoStrategy, transport="asgi")
        mcp_public = Context(_EchoStrategy, transport="bridge")

    app = _App()

    assert resolve_mcp_context(app, transport="bridge") is app.mcp_public
    assert resolve_mcp_context(app, context="mcp_public") is app.mcp_public


def test_resolve_mcp_context_prefers_context_name_over_transport_selector():
    web_public = Context(_EchoStrategy, transport="asgi")
    web_admin = Context(_EchoStrategy, transport="asgi")

    class _App(metaclass=ApplicationMeta):
        asgi_public = web_public
        asgi_admin = web_admin
        mcp_private = Context(McpStrategy, transport=web_public, params={"profile": "private"})

    app = _App()

    assert resolve_mcp_context(app, transport="asgi_public") is app.asgi_public


def test_resolve_mcp_context_raises_when_transport_ambiguous():
    class _App(metaclass=ApplicationMeta):
        asgi_public = Context(_EchoStrategy, transport="asgi")
        asgi_admin = Context(_EchoStrategy, transport="asgi")

    app = _App()

    import pytest

    with pytest.raises(ValueError, match="ambiguous"):
        resolve_mcp_context(app, transport="asgi")


def test_mcp_adapter_call_tool_carries_entrypoint_context_metadata_per_named_context():
    class _App(metaclass=ApplicationMeta):
        web_public = Context(_EchoStrategy, transport="asgi", params={"profile": "public"})
        web_admin = Context(_EchoStrategy, transport="asgi", params={"profile": "admin"})
        mcp_public = Context(McpStrategy, transport=web_public, params={"mcp_profile": "public"})
        mcp_admin = Context(McpStrategy, transport="admin")

    app = _App()
    add_action(
        app,
        name="inspect",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
        transports=["mcp"],
        handler=lambda payload, context: {
            "entrypoint_name": context.metadata["entrypoint_context"]["name"],
            "entrypoint_transport": context.metadata["entrypoint_context"]["transport"],
            "received": payload["value"],
        },
    )

    public = McpAdapter.from_application(app, context="mcp_public")
    admin = McpAdapter.from_application(app, context=app.mcp_admin)

    public_payload = public.call_tool("inspect", {"value": "one"})
    admin_payload = admin.call_tool("inspect", {"value": "two"})

    assert public_payload["content"][0]["json"] == {
        "entrypoint_name": "mcp_public",
        "entrypoint_transport": "web_public",
        "received": "one",
    }
    assert admin_payload["content"][0]["json"] == {
        "entrypoint_name": "mcp_admin",
        "entrypoint_transport": "admin",
        "received": "two",
    }
