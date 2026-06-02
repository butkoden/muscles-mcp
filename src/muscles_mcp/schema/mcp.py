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


class McpJsonMimeType(_ValueObject):
    def normalize(self, value):
        return str(value).strip().lower()

    def validate(self, value):
        if value != "application/json":
            raise ValueError("MCP JSON resources must use application/json mime type")
        return True


class McpToolDescriptor(_MusclesModel):
    name = _Column(_ValueObjectField(value_object_class=_NonEmptyStringValue), nullable=False)
    description = _Column(_Text, default="")
    input_schema = _Column(_Json, default=dict)

    @classmethod
    def from_action_contract(cls, action: dict[str, Any]):
        return cls(
            name=action["name"],
            description=action.get("description", ""),
            input_schema=action.get("input_schema", {"type": "object", "properties": {}}),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": str(self.name),
            "description": self.description or "",
            "input_schema": _json_value(self.input_schema, {"type": "object", "properties": {}}),
        }


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
    arguments = _Column(_Json, default=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]):
        return cls(name=payload.get("name"), arguments=payload.get("arguments") or {})

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": str(self.name),
            "arguments": _json_value(self.arguments, {}),
        }


class McpToolCallResult(_MusclesModel):
    content = _Column(_List, default=list)
    is_error = _Column(_Boolean, default=False)
    error = _Column(_Json, default=None)

    @classmethod
    def success(cls, value: Any):
        return cls(content=[McpToolJsonContent.from_json(value).to_payload()], is_error=False, error=None)

    @classmethod
    def failure(cls, code: str, message: str, data: Any = None):
        error = McpErrorPayload(code=code, message=message, data=data).to_payload()
        return cls(content=[], is_error=True, error=error)

    def to_payload(self) -> dict[str, Any]:
        if self.is_error:
            return {"isError": True, "error": _json_value(self.error)}
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
    "McpToolDescriptor",
    "McpResourceDescriptor",
    "McpResourceContent",
    "McpToolJsonContent",
    "McpErrorPayload",
    "McpToolCallRequest",
    "McpToolCallResult",
    "McpResourceReadResult",
)
