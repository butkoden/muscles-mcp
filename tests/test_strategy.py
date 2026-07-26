from muscles.core import (
    ApplicationMeta,
    BaseStrategy,
    Context,
    Integer,
    Model,
    String,
    StreamEvent,
    StreamResult,
    Column,
)

import pytest

from muscles_mcp import McpAdapter, McpError, McpStrategy, build_model_json_schema


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


def add_action(app, **options):
    handler = options.pop("handler")
    app.action(**options)(handler)


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

    add_action(
        app,
        name="bookings.create",
        description="Create booking",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["mcp"],
        handler=create_booking,
    )
    return app, calls


def _mcp_metadata(
    route: str,
    full_route: str,
    name: str,
    server: str,
    token: str | None = None,
) -> dict:
    return {
        "mcp": {
            "route": route,
            "full_route": full_route,
            "name": name,
            "transport": "mcp",
            "server": server,
            "servers": [server],
            **({"token": token} if token is not None else {}),
        }
    }


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


def test_mcp_strategy_auto_builds_schema_for_model_input():
    class BookingCreate(Model):
        title = Column(String)
        guest_count = Column(Integer, default=1)

    class _ModelApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)

    app = _ModelApp()
    add_action(
        app,
        name="bookings.model",
        description="Create booking from model",
        input_schema=BookingCreate,
        handler=lambda payload, context: {"id": 1, "payload": payload},
    )

    tools = app.context.execute(operation="list_tools")

    assert tools == [
        {
            "name": "bookings.model",
            "description": "Create booking from model",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "guest_count": {"type": "integer", "default": 1},
                },
            },
        }
    ]

    inspected = app.context.execute(operation="read_resource", uri="muscles://app/actions")["contents"][0]["json"]
    assert inspected[0]["input_schema"]["properties"]["title"]["type"] == "string"


def test_mcp_adapter_is_facade_over_strategy_projection():
    app, calls = _build_mcp_app()

    adapter = McpAdapter.from_application(app)

    assert adapter.list_tools() == app.context.execute(operation="list_tools")
    response = adapter.call_tool("bookings.create", {"title": "Facade"})

    assert calls == [("bookings.create", {"title": "Facade"}, "mcp")]
    assert response["content"][0]["json"]["title"] == "Facade"


def test_mcp_metadata_registration_supports_route_metadata():
    class _RoutesApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)

    app = _RoutesApp()

    add_action(
        app,
        name="bookings.create",
        description="Create booking",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["mcp"],
        metadata=_mcp_metadata(
            route="/bookings/create",
            full_route="/api/bookings/create",
            name="bookings.create",
            server="public",
            token="SIMSIM-PUBLIC",
        ),
        handler=lambda payload, context: {
            "title": payload["title"],
            "guest_count": payload.get("guest_count", 1),
        },
    )

    tools = app.context.execute(operation="list_tools")
    assert tools == [
        {
            "name": "bookings.create",
            "description": "Create booking",
            "input_schema": BOOKING_INPUT_SCHEMA,
        }
    ]

    actions_resource = app.context.execute(operation="read_resource", uri="muscles://app/actions")
    action_entry = actions_resource["contents"][0]["json"][0]
    assert action_entry["metadata"]["mcp"]["route"] == "/bookings/create"
    assert action_entry["metadata"]["mcp"]["full_route"] == "/api/bookings/create"
    assert action_entry["metadata"]["mcp"]["name"] == "bookings.create"
    assert action_entry["metadata"]["mcp"]["transport"] == "mcp"
    assert action_entry["name"] == "bookings.create"
    assert action_entry["description"] == "Create booking"

    response = app.context.execute(
        operation="call_tool",
        name="bookings.create",
        arguments={"title": "Route based"},
    )
    assert response == {
        "content": [
            {
                "type": "json",
                "json": {
                    "title": "Route based",
                    "guest_count": 1,
                },
            }
        ]
    }


def test_mcp_metadata_registration_accepts_model_schema_without_side_effects():
    class BookingCreate(Model):
        title = Column(String, nullable=False, min_length=1)
        guest_count = Column(Integer, default=1)

    class _RoutesModelApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)

    app = _RoutesModelApp()

    add_action(
        app,
        name="bookings.model",
        input_schema=build_model_json_schema(BookingCreate),
        transports=["mcp"],
        metadata=_mcp_metadata(
            route="/bookings/model",
            full_route="/api/bookings/model",
            name="bookings.model",
            server="public",
        ),
        handler=lambda payload, context: payload,
    )

    tools = app.context.execute(operation="list_tools")
    assert tools == [
        {
            "name": "bookings.model",
            "description": "",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "guest_count": {"type": "integer", "default": 1},
                },
                "required": ["title"],
            },
        }
    ]

    response = app.context.execute(
        operation="call_tool",
        name="bookings.model",
        arguments={"title": "M"},
    )
    assert response == {
        "content": [
            {
                "type": "json",
                "json": {"title": "M"},
            }
        ]
    }


def test_mcp_metadata_registration_supports_server_filtering_and_tokens():
    class BookingCreate(Model):
        title = Column(String, nullable=False, min_length=1)
        guest_count = Column(Integer, default=1)

    class _McpServerApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)

    app = _McpServerApp()

    add_action(
        app,
        name="bookings.create",
        input_schema=build_model_json_schema(BookingCreate),
        transports=["mcp"],
        metadata=_mcp_metadata(
            route="/bookings/create",
            full_route="/mcp/public/bookings/create",
            name="bookings.create",
            server="public",
            token="SIMSIM-PUBLIC",
        ),
        handler=lambda payload, context: {
            "title": payload["title"],
            "guest_count": payload.get("guest_count", 1),
            "server": payload.get("server"),
        },
    )

    add_action(
        app,
        name="bookings.health",
        input_schema={"type": "object", "properties": {}},
        transports=["mcp"],
        metadata=_mcp_metadata(
            route="/bookings/list",
            full_route="/mcp/public/bookings/list",
            name="bookings.health",
            server="public",
            token="SIMSIM-PUBLIC",
        ),
        handler=lambda payload, context: {"ok": True},
    )

    public_tools = app.context.execute(operation="list_tools", server="public")
    assert [tool["name"] for tool in public_tools] == ["bookings.create", "bookings.health"]

    admin_tools = app.context.execute(operation="list_tools", server="admin")
    assert admin_tools == []

    assert app.context.execute(operation="list_tools", server="public", token="SIMSIM-PUBLIC") == public_tools
    assert app.context.execute(operation="list_tools", server="public", token="WRONG") == []

    denied_response = app.context.execute(
        operation="call_tool",
        server="public",
        token="WRONG",
        name="bookings.create",
        arguments={"title": "Need token"},
    )
    assert denied_response["isError"] is True
    assert denied_response["error"]["code"] == "permission_denied"

    allowed_response = app.context.execute(
        operation="call_tool",
        server="public",
        token="SIMSIM-PUBLIC",
        name="bookings.create",
        arguments={"title": "Need token"},
    )
    assert allowed_response["content"][0]["json"] == {
        "title": "Need token",
        "guest_count": 1,
        "server": None,
    }

def test_mcp_strategy_state_is_scoped_to_container_application():
    app_a, _ = _build_mcp_app()

    class _OtherMcpApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)

    app_b = _OtherMcpApp()
    add_action(
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


def test_mcp_strategy_lists_stream_capability_from_core_inspect_contract():
    app, _ = _build_mcp_app()
    add_action(
        app,
        name="bookings.stream",
        input_schema={"type": "object", "properties": {}},
        transports=["mcp"],
        stream_output=True,
        stream_metadata={"event_types": ["progress", "result"]},
        handler=lambda payload, context: StreamResult(source=[]),
    )

    tools = app.context.execute(operation="list_tools")
    stream_tool = next(tool for tool in tools if tool["name"] == "bookings.stream")

    assert stream_tool["stream"]["enabled"] is True
    assert stream_tool["stream"]["event_types"] == ["progress", "result"]


def test_mcp_strategy_projects_core_stream_events_without_second_handler_call():
    calls = []

    def stream_booking(payload, context):
        calls.append((payload, context.transport))
        return StreamResult(
            source=[
                StreamEvent(type="progress", data={"step": 1}, event_id="evt-1"),
                StreamEvent(type="log", data={"message": "working"}),
                StreamEvent(type="result", data={"ok": True}),
            ]
        )

    app, _ = _build_mcp_app()
    add_action(
        app,
        name="bookings.stream_call",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["mcp"],
        stream_output=True,
        handler=stream_booking,
    )

    response = app.context.execute(
        operation="call_tool",
        name="bookings.stream_call",
        arguments={"title": "Call"},
    )

    assert calls == [({"title": "Call"}, "mcp")]
    assert response == {
        "content": [
            {"type": "json", "json": {"event": "progress", "data": {"step": 1}, "id": "evt-1", "metadata": {}}},
            {"type": "json", "json": {"event": "log", "data": {"message": "working"}, "id": None, "metadata": {}}},
            {"type": "json", "json": {"event": "result", "data": {"ok": True}, "id": None, "metadata": {}}},
        ]
    }


def test_mcp_adapter_projects_stream_error_event_as_mcp_friendly_error_response():
    def stream_booking(payload, context):
        def source():
            yield StreamEvent(type="progress", data={"step": 1})
            raise RuntimeError("stream failed")

        return StreamResult(source=source())

    app, _ = _build_mcp_app()
    add_action(
        app,
        name="bookings.stream_error",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["mcp"],
        stream_output=True,
        handler=stream_booking,
    )
    adapter = McpAdapter.from_application(app)

    response = adapter.call_tool("bookings.stream_error", {"title": "Call"})

    assert response["isError"] is True
    assert response["content"][0]["json"]["event"] == "progress"
    assert response["content"][1]["json"]["event"] == "error"
    assert response["content"][1]["json"]["data"]["code"] == "stream_error"


def test_mcp_strategy_accepts_operation_and_tool_payload_from_request_contract():
    app, _ = _build_mcp_app()

    response = app.context.execute(
        request={
            "operation": "call_tool",
            "name": "bookings.create",
            "arguments": {"title": "From contract", "guest_count": 2},
        }
    )

    assert response == {
        "content": [
            {
                "type": "json",
                "json": {"id": 1, "title": "From contract", "guest_count": 2},
            }
        ]
    }


def test_mcp_strategy_passes_entrypoint_context_to_action_metadata():
    app, _ = _build_mcp_app()
    metadata_calls = []

    @app.action(
        name="bookings.meta",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["mcp"],
    )
    def bookings_meta(payload, context):
        metadata_calls.append(context.metadata)
        return {"title": payload["title"]}

    response = app.context.execute(
        operation="call_tool",
        name="bookings.meta",
        arguments={"title": "Context"},
    )

    assert response == {
        "content": [
            {
                "type": "json",
                "json": {"title": "Context"},
            }
        ]
    }
    assert metadata_calls == [
        {
            "entrypoint_context": {
                "name": "context",
                "transport": None,
            },
        }
    ]


def test_mcp_strategy_preserves_entrypoint_context_when_transport_is_nested_context():
    asgi_public_context = Context(McpStrategy, transport="asgi")

    class _AppWithNestedTransport(metaclass=ApplicationMeta):
        asgi_public = asgi_public_context
        mcp_private = Context(McpStrategy, transport=asgi_public_context)

    app = _AppWithNestedTransport()
    metadata = []

    @app.action(
        name="bookings.nested",
        input_schema=BOOKING_INPUT_SCHEMA,
        transports=["mcp"],
    )
    def nested_booking(payload, context):
        metadata.append(context.metadata)
        return {"title": payload["title"]}

    response = app.mcp_private.execute(
        operation="call_tool",
        name="bookings.nested",
        arguments={"title": "Nested"},
    )

    assert response == {
        "content": [
            {
                "type": "json",
                "json": {"title": "Nested"},
            }
        ]
    }
    assert metadata == [
        {
            "entrypoint_context": {
                "name": "mcp_private",
                "transport": "asgi_public",
            }
        }
    ]


def test_mcp_strategy_rejects_unknown_operation_in_request_contract():
    app, _ = _build_mcp_app()

    with pytest.raises(McpError) as exc:
        app.context.execute(
            request={
                "operation": "bad_operation",
                "name": "bookings.create",
            }
        )
    assert exc.value.code == "invalid_request"


def test_mcp_strategy_accepts_list_resources_from_request_contract():
    app, _ = _build_mcp_app()

    resources = app.context.execute(request={"operation": "list_resources"})
    uris = {item["uri"] for item in resources}

    assert uris == {
        "muscles://app/inspect",
        "muscles://app/actions",
        "muscles://app/capabilities",
        "muscles://app/architecture",
        "muscles://app/routes",
        "muscles://app/schemas",
        "muscles://app/rules",
    }


def test_mcp_strategy_projects_capabilities_and_architecture_resources():
    app, _ = _build_mcp_app()
    registry = app.__muscles_registry__
    registry.packages["ai"] = {"namespace": "ai", "name": "AiPackage"}
    registry.inspection_providers["ai"] = lambda: {
        "role": "AI runtime",
        "architecture": {
            "rules": [
                {
                    "id": "ai.state_change.confirmation",
                    "severity": "error",
                    "summary": "State-changing actions require confirmation.",
                }
            ]
        },
    }

    capabilities = app.context.execute(
        operation="read_resource",
        uri="muscles://app/capabilities",
    )["contents"][0]["json"]
    architecture = app.context.execute(
        operation="read_resource",
        uri="muscles://app/architecture",
    )["contents"][0]["json"]

    assert capabilities["ai"]["role"] == "AI runtime"
    assert architecture["capabilities"]["ai"]["architecture"]["rules"][0]["id"] == (
        "ai.state_change.confirmation"
    )


def test_mcp_strategy_accepts_read_resource_from_request_contract():
    app, _ = _build_mcp_app()

    payload = app.context.execute(
        request={
            "operation": "read_resource",
            "uri": "muscles://app/actions",
        }
    )
    assert payload["contents"][0]["uri"] == "muscles://app/actions"
    assert payload["contents"][0]["mimeType"] == "application/json"
    assert isinstance(payload["contents"][0]["json"], list)
    assert payload["contents"][0]["json"][0]["name"] == "bookings.create"


def test_mcp_strategy_supports_server_filtering_via_request_contract():
    app, _ = _build_mcp_app()
    payload = app.context.execute(
        request={
            "operation": "list_tools",
            "server": "legacy",
            "token": "notused",
        }
    )
    assert [tool["name"] for tool in payload] == ["bookings.create"]
