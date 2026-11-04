from typing import Any, Type

from muscles.core import Model


def build_model_json_schema(model: Type[Model] | Model) -> dict[str, Any]:
    """Build a JSON Schema fragment from a Muscles Model class or instance."""

    if isinstance(model, type):
        model_instance = model()
    else:
        model_instance = model

    if not isinstance(model_instance, Model):
        raise TypeError("Expected a Muscles Model class or instance")

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, column in model_instance.columns.items():
        field_schema: dict[str, Any] = {
            "type": column.field_type.schema_type,
        }
        if column.description:
            field_schema["description"] = column.description
        if column.default is not None:
            field_schema["default"] = column.default
        if column.min_length is not None:
            field_schema["minLength"] = column.min_length
        if column.max_length is not None:
            field_schema["maxLength"] = column.max_length
        properties[name] = field_schema
        if column.nullable is False:
            required.append(name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


__all__ = ["build_model_json_schema"]

