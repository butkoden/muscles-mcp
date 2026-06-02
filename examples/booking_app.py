from muscles.core import ApplicationMeta, Column, Context, Integer, Model, String, register_action
from muscles_mcp import McpStrategy


class BookingCreate(Model):
    title = Column(String, nullable=False, min_length=1)
    guest_count = Column(Integer, default=1)


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
    input_schema=BookingCreate,
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
