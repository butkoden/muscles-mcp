from muscles.core import ApplicationMeta, Column, Context, Integer, Model, String
from muscles_mcp import McpStrategy, build_model_json_schema
from muscles.asgi import AsgiStrategy


class BookingCreate(Model):
    title = Column(String, nullable=False, min_length=1)
    guest_count = Column(Integer, default=1)


class BookingApp(metaclass=ApplicationMeta):
    # MCP entrypoints bind to concrete entrypoint contexts.
    asgi_public = Context(AsgiStrategy, params={"profile": "public"})
    asgi_admin = Context(AsgiStrategy, params={"profile": "admin"})

    mcp_public = Context(McpStrategy, transport=asgi_public, params={"mcp_profile": "public"})
    mcp_admin = Context(McpStrategy, transport=asgi_admin, params={"mcp_profile": "admin"})


app = BookingApp()


def _mcp_metadata(route: str, route_prefix: str, name: str, server: str, token: str | None = None):
    return {
        "mcp": {
            "route": route,
            "full_route": f"{route_prefix.rstrip('/')}/{route.lstrip('/')}".replace("//", "/"),
            "name": name,
            "transport": "mcp",
            "server": server,
            "servers": [server],
            **({"token": token} if token else {}),
        }
    }


@app.action(
    name="bookings.create",
    description="Create a booking request",
    input_schema=build_model_json_schema(BookingCreate),
    transports=["mcp"],
    metadata=_mcp_metadata("/create", "/bookings", "bookings.create", "public", "SIMSIM-PUBLIC"),
)
def create_booking(payload, context):
    return {
        "id": 1,
        "title": payload["title"],
        "guest_count": payload.get("guest_count", 1),
        "transport": context.transport,
    }


@app.action(
    name="admin.health",
    input_schema={"type": "object", "properties": {}},
    transports=["mcp"],
    metadata=_mcp_metadata("/health", "/admin", "admin.health", "admin"),
)
def admin_health(payload, context):
    return {"ok": True}


if __name__ == "__main__":
    print(app.mcp_public.execute(operation="list_tools"))
    print(app.mcp_admin.execute(operation="list_tools"))
    print(
        app.mcp_public.execute(
            operation="call_tool",
            name="bookings.create",
            arguments={"title": "Discovery call", "guest_count": 2},
        )
    )
