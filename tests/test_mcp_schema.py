import inspect

from muscles.core import Model

from muscles_mcp.schema import mcp


def test_mcp_protocol_models_live_under_schema_mcp_without_core_name_collisions():
    assert mcp.__name__.endswith("muscles_mcp.schema.mcp")
    assert not hasattr(mcp, "Model")
    assert not hasattr(mcp, "Schema")
    assert not hasattr(mcp, "Response")

    exported_model_names = set(mcp.__all__)

    assert exported_model_names == {
        "McpJsonMimeType",
        "McpOperation",
        "McpProtocolRequest",
        "McpToolDescriptor",
        "McpResourceDescriptor",
        "McpResourceContent",
        "McpToolJsonContent",
        "McpStreamEventContent",
        "McpErrorPayload",
        "McpToolCallRequest",
        "McpToolCallResult",
        "McpResourceReadResult",
    }


def test_mcp_protocol_models_inherit_muscles_model_contract():
    for name in mcp.__all__:
        obj = getattr(mcp, name)
        if not inspect.isclass(obj):
            continue
        if name in {"McpJsonMimeType", "McpOperation", "McpProtocolRequest"}:
            continue
        assert issubclass(obj, Model)


def test_mcp_tool_call_request_parses_incoming_message_with_value_object():
    request = mcp.McpToolCallRequest.from_payload(
        {
            "name": "bookings.create",
            "arguments": {"title": "Call"},
        }
    )

    assert str(request.name) == "bookings.create"
    assert request.to_payload()["arguments"] == {"title": "Call"}
    assert request.to_payload() == {
        "name": "bookings.create",
        "arguments": {"title": "Call"},
    }


def test_mcp_protocol_request_resolves_known_operation():
    payload = mcp.McpProtocolRequest.from_payload(
        {
            "operation": "list_tools",
            "uri": "muscles://app/inspect",
            "name": "bookings.create",
            "arguments": {"title": "Call"},
        }
    )
    assert str(payload.operation) == "list_tools"
    assert str(payload.uri) == "muscles://app/inspect"
    assert str(payload.name) == "bookings.create"
    assert payload.arguments == {"title": "Call"}


def test_mcp_tool_call_result_forms_outgoing_success_payload():
    result = mcp.McpToolCallResult.success({"id": 1})

    assert result.to_payload() == {
        "content": [
            {
                "type": "json",
                "json": {"id": 1},
            }
        ]
    }


def test_mcp_tool_call_result_forms_outgoing_error_payload():
    result = mcp.McpToolCallResult.failure(
        code="invalid_params",
        message="Missing title",
        data={"path": []},
    )

    assert result.to_payload() == {
        "isError": True,
        "error": {
            "code": "invalid_params",
            "message": "Missing title",
            "data": {"path": []},
        },
    }


def test_mcp_resource_read_result_uses_json_mime_type_value_object():
    result = mcp.McpResourceReadResult.from_json(
        "muscles://app/actions",
        [{"name": "bookings.create"}],
    )

    assert result.to_payload() == {
        "contents": [
            {
                "uri": "muscles://app/actions",
                "mimeType": "application/json",
                "json": [{"name": "bookings.create"}],
            }
        ]
    }
