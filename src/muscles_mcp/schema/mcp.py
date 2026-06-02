from __future__ import annotations

import json as _json
from typing import Any

from muscles.core import (
    Boolean as _Boolean,
    Column as _Column,
    Json as _Json,
    List as _List,
    Model as _MusclesModel,
    NonEmptyStringValue as _NonEmptyStringValue,
    Text as _Text,
    ValueObject as _ValueObject,
    ValueObjectField as _ValueObjectField,
)


def _json_value(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return _json.loads(value)
        except Exception:
            return fallback
    return value


def _json_payload(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return _json.loads(value)
        except Exception:
            return value
    return value


class McpJsonMimeType(_ValueObject):
    def normalize(self, value):
        return str(value).strip().lower()

    def validate(self, value):
        if value != "application/json":
            raise ValueError("MCP JSON resources must use application/json mime type")
        return True


class McpOperation(_ValueObject):
    """Operation names supported by the MCP strategy."""

    allowed = {
        "list_tools",
        "list_resources",
        "read_resource",
        "call_tool",
    }

    def normalize(self, value):
        return str(value).strip().lower()

    def validate(self, value):
        if value not in self.allowed:
            raise ValueError(f"Unknown MCP operation: {value}")
        return True


class McpJsonPayload(_ValueObject):
    """Normalized JSON payload holder for MCP arguments and request bodies."""

    def normalize(self, value):
        if isinstance(value, McpJsonPayload):
            return value.value
        if value is None:
            return {}
        if isinstance(value, str):
            try:
                value = _json.loads(value)
            except Exception:
                raise ValueError(f"Invalid JSON payload: {value!r}")
        if not isinstance(value, dict):
            raise ValueError(f"Invalid MCP payload value: {type(value)!r}")
        return value

    def validate(self, value):
        if not isinstance(value, dict):
            raise ValueError(f"Invalid MCP payload value: {value!r}")
        return True

    def __eq__(self, other):
        if isinstance(other, dict):
            return self.value == other
        return super().__eq__(other)


def _payload_value(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, _ValueObject):
        return value.to_primitive()
    return _json_value(value, fallback)


class McpProtocolRequest(_MusclesModel):
    operation = _Column(_ValueObjectField(value_object_class=McpOperation), nullable=False)
    uri = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), default=None)
    name = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), default=None)
    arguments = _Column(_ValueObjectField(value_object_class=McpJsonPayload), default=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]):
        if payload is None:
            raise ValueError("Payload is required")
        return cls(
            operation=payload.get("operation"),
            uri=payload.get("uri"),
            name=payload.get("name"),
            arguments=_json_payload(payload.get("arguments"), {}),
        )


class McpToolDescriptor(_MusclesModel):
    name = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), nullable=False)
    description = _Column(_Text, default="")
    input_schema = _Column(_Json, default=dict)
    stream = _Column(_Json, default=None)

    @classmethod
    def from_action_contract(cls, action: dict[str, Any]):
        return cls(
            name=action["name"],
            description=action.get("description", ""),
            input_schema=action.get("input_schema", {"type": "object", "properties": {}}),
            stream=action.get("stream") if action.get("stream_output") else None,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "name": str(self.name),
            "description": self.description or "",
            "input_schema": _json_value(self.input_schema, {"type": "object", "properties": {}}),
        }
        stream = _json_value(self.stream)
        if stream is not None:
            payload["stream"] = stream
        return payload


class McpResourceDescriptor(_MusclesModel):
    uri = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), nullable=False)
    name = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), nullable=False)

    def to_payload(self) -> dict[str, Any]:
        return {
            "uri": str(self.uri),
            "name": str(self.name),
        }


class McpResourceContent(_MusclesModel):
    uri = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), nullable=False)
    mime_type = _Column(_ValueObjectField(value_object_class=McpJsonMimeType), nullable=False)
    json = _Column(_Json, default=dict)

    @classmethod
    def from_json(cls, uri: str, value: Any):
        return cls(uri=uri, mime_type="application/json", json=value)

    def to_payload(self) -> dict[str, Any]:
        return {
            "uri": str(self.uri),
            "mimeType": str(self.mime_type),
            "json": _json_value(self.json, {}),
        }


class McpToolJsonContent(_MusclesModel):
    type = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), default="json")
    json = _Column(_Json, default=dict)

    @classmethod
    def from_json(cls, value: Any):
        return cls(type="json", json=value)

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": str(self.type),
            "json": _json_value(self.json, {}),
        }


class McpStreamEventContent(_MusclesModel):
    event = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), nullable=False)
    data = _Column(_Json, default=dict)
    event_id = _Column(_Text, default=None)
    metadata = _Column(_Json, default=dict)

    @classmethod
    def from_core_event(cls, event):
        return cls(
            event=event.type,
            data=event.data,
            event_id=event.event_id,
            metadata=dict(event.metadata),
        )

    def to_payload(self) -> dict[str, Any]:
        return McpToolJsonContent.from_json(
            {
                "event": str(self.event),
                "data": _json_value(self.data, {}),
                "id": self.event_id,
                "metadata": _json_value(self.metadata, {}),
            }
        ).to_payload()


class McpErrorPayload(_MusclesModel):
    code = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), nullable=False)
    message = _Column(_Text, default="")
    data = _Column(_Json, default=None)

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": str(self.code),
            "message": self.message or "",
            "data": _json_value(self.data),
        }


class McpToolCallRequest(_MusclesModel):
    name = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), nullable=False)
    arguments = _Column(_ValueObjectField(value_object_class=McpJsonPayload), default=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]):
        return cls(name=payload.get("name"), arguments=payload.get("arguments") or {})

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": str(self.name),
            "arguments": _payload_value(self.arguments, {}),
        }


class McpToolCallResult(_MusclesModel):
    content = _Column(_List, default=list)
    is_error = _Column(_Boolean, default=False)
    error = _Column(_Json, default=None)

    @classmethod
    def success(cls, value: Any):
        return cls(content=[McpToolJsonContent.from_json(value).to_payload()], is_error=False, error=None)

    @classmethod
    def stream(cls, stream_result: Any):
        from muscles.core import stream_events

        content = []
        is_error = False
        for event in stream_events(stream_result):
            if event.type == "error":
                is_error = True
            content.append(McpStreamEventContent.from_core_event(event).to_payload())
        return cls(content=content, is_error=is_error, error=None)

    @classmethod
    def failure(cls, code: str, message: str, data: Any = None):
        error = McpErrorPayload(code=code, message=message, data=data).to_payload()
        return cls(content=[], is_error=True, error=error)

    def to_payload(self) -> dict[str, Any]:
        if self.is_error:
            payload: dict[str, Any] = {"isError": True}
            if self.content:
                payload["content"] = self.content
            if self.error is not None:
                payload["error"] = _json_value(self.error)
            return payload
        return {"content": self.content or []}


class McpResourceReadResult(_MusclesModel):
    contents = _Column(_List, default=list)

    @classmethod
    def from_json(cls, uri: str, value: Any):
        return cls(contents=[McpResourceContent.from_json(uri, value).to_payload()])

    def to_payload(self) -> dict[str, Any]:
        return {"contents": self.contents or []}


__all__ = (
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
)
