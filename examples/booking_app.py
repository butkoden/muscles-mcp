from muscles.core import ApplicationMeta, Column, Context, Integer, Model, String, register_action
from muscles_mcp import McpStrategy


class BookingCreate(Model):
    title = Column(String, nullable=False, min_length=1)
    guest_count = Column(Integer, default=1)


def model_json_schema(model_class):
    model = model_class()
    properties = {}
    required = []
    for name, column in model.columns.items():
        field_schema = {"type": column.field_type.schema_type}
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
    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


class BookingApp(metaclass=ApplicationMeta):
    context = Context(McpStrategy)


app = BookingApp()


def create_booking(payload, context):
    return {
        "id": 1,
        "title": payload["title"],
        "guest_count": payload.get("guest_count", 1),
        "transport": context.transport,
    }


register_action(
    app,
    name="bookings.create",
    description="Create a booking request",
    input_schema=model_json_schema(BookingCreate),
    output_schema={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "title": {"type": "string"},
            "guest_count": {"type": "integer"},
            "transport": {"type": "string"},
        },
    },
    transports=["mcp"],
    handler=create_booking,
)


if __name__ == "__main__":
    print(app.context.execute(operation="list_tools"))
    print(
        app.context.execute(
            operation="call_tool",
            name="bookings.create",
            arguments={"title": "Discovery call", "guest_count": 2},
        )
    )
