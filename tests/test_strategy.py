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
    register_action,
)

import pytest

from muscles_mcp import McpAdapter, McpError, McpRouter, McpStrategy


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


def test_mcp_strategy_auto_builds_schema_for_model_input():
    class BookingCreate(Model):
        title = Column(String)
        guest_count = Column(Integer, default=1)

    class _ModelApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)

    app = _ModelApp()
    register_action(
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


def test_mcp_router_registers_action_with_route_metadata():
    class _RoutesApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)
        mcp = McpRouter(route_prefix="/api")

    app = _RoutesApp()

    @app.mcp(route="/bookings/create", description="Create booking", input_schema=BOOKING_INPUT_SCHEMA)
    def create_booking(payload, context):
        return {
            "title": payload["title"],
            "guest_count": payload.get("guest_count", 1),
        }

    tools = app.context.execute(operation="list_tools")
    assert tools == [
        {
            "name": "bookings.create",
            "description": "Create booking",
            "input_schema": BOOKING_INPUT_SCHEMA,
        }
    ]

    actions_resource = app.context.execute(operation="read_resource", uri="muscles://app/actions")
    assert actions_resource == {
        "contents": [
            {
                "uri": "muscles://app/actions",
                "mimeType": "application/json",
                "json": [
                    {
                        "name": "bookings.create",
                        "description": "Create booking",
                        "input_schema": BOOKING_INPUT_SCHEMA,
                        "output_schema": {"type": "object", "properties": {}},
                        "rules": [],
                        "handler_ref": "test_strategy.create_booking",
                        "transports": ["mcp"],
                        "stream_output": False,
                        "stream": {
                            "enabled": False,
                            "event_types": ["error", "log", "progress", "result"],
                            "cooperative_cancellation": True,
                            "backpressure": "transport-bounded",
                            "metadata": {},
                        },
                        "metadata": {
                            "mcp": {
                                "route": "/bookings/create",
                                "full_route": "/api/bookings/create",
                                "name": "bookings.create",
                                "transport": "mcp",
                            }
                        },
                    }
                ],
            }
        ]
    }

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


def test_mcp_router_accepts_model_schema_and_runs_validation_without_core_to_json_side_effects():
    class BookingCreate(Model):
        title = Column(String, nullable=False, min_length=1)
        guest_count = Column(Integer, default=1)

    class _RoutesModelApp(metaclass=ApplicationMeta):
        context = Context(McpStrategy)
        mcp = McpRouter(route_prefix="/api")

    app = _RoutesModelApp()

    @app.mcp(route="/bookings/model", name="bookings.model", input_schema=BookingCreate)
    def create_booking_model(payload, context):
        return payload

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


def test_mcp_strategy_lists_stream_capability_from_core_inspect_contract():
    app, _ = _build_mcp_app()
    register_action(
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
    register_action(
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
    register_action(
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
        "muscles://app/routes",
        "muscles://app/schemas",
        "muscles://app/rules",
    }


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
