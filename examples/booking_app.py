from muscles.core import ApplicationMeta, Column, Context, Integer, Model, String
from muscles_mcp import McpRouter, McpStrategy


class BookingCreate(Model):
    title = Column(String, nullable=False, min_length=1)
    guest_count = Column(Integer, default=1)


class BookingApp(metaclass=ApplicationMeta):
    context = Context(McpStrategy)
    mcp = McpRouter(route_prefix="/api")


app = BookingApp()


@app.mcp.server(name="public", route_prefix="/bookings", token="SIMSIM-PUBLIC")
def public_server():
    pass


@public_server.action(route="/create", name="bookings.create", input_schema=BookingCreate)
def create_booking(payload, context):
    return {
        "id": 1,
        "title": payload["title"],
        "guest_count": payload.get("guest_count", 1),
        "transport": context.transport,
    }


if __name__ == "__main__":
    print(app.context.execute(operation="list_tools"))
    print(
        app.context.execute(
            operation="call_tool",
            name="bookings.create",
            arguments={"title": "Discovery call", "guest_count": 2},
        )
    )
