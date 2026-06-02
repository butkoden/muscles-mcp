# Muscles MCP

Model Context Protocol projection for Muscles.

This package exposes a Muscles application to AI tools through MCP without
copying application logic into the MCP layer.

## Concept Guardrails

- Muscles remains the source of truth for actions, schemas, rules, context,
  permissions, and execution.
- MCP tools/resources must be generated from `inspect_application(app)`.
- The MCP layer must not invent its own routing, validation, auth, action
  registry, or business model.
- A use case implemented once in Muscles should become available through MCP
  without rewriting the use case.
- Machine-readable metadata is a product feature, not an internal detail.
- MCP is a protocol projection over `ApplicationMeta`, `Context`, the
  application-scoped registry, `ActionContract`, and `ActionDispatcher`; it is
  not a separate runtime next to Muscles.

## Initial Goal

Expose a Muscles app as MCP tools and resources, backed by
`inspect_application(app)` / `muscles inspect --json` compatible contract data.

## Current Stage (Issue #8)

Implemented MCP projection as a Muscles application strategy:

- `McpStrategy` can be connected through `Context(McpStrategy)`;
- `McpAdapter` remains a compatibility facade over the same strategy logic;
- `list_tools()` from contract `actions`;
- `list_resources()` for canonical MCP URIs:
  - `muscles://app/inspect`
  - `muscles://app/actions`
  - `muscles://app/routes`
  - `muscles://app/schemas`
  - `muscles://app/rules`
- `read_resource(uri)` returns stable JSON payload per resource;
- `call_tool()` delegates to Muscles core `ActionDispatcher` with
  `transport="mcp"` (no business-logic copy);
- tool input validation is performed by Muscles core;
- permission/rule denial is returned as structured MCP error mapped from core
  errors.
- MCP protocol messages are represented by Muscles-based models in
  `muscles_mcp.schema.mcp`;
- MCP schema module and class names are protocol-specific and do not reuse core
  names such as `schema.py`, `model.py`, `response.py`, `Model`, `Schema`, or
  `Response`.

### Run tests

```bash
python -m pytest -q
```

User docs:

- English: [docs/mcp-projection.en.md](docs/mcp-projection.en.md)
- Русский: [docs/mcp-projection.ru.md](docs/mcp-projection.ru.md)

Runnable example:

- [examples/booking_app.py](examples/booking_app.py)

## Detailed Usage Example

This example shows the intended architecture:

- Muscles owns the application contract and business execution.
- `muscles-mcp` exposes that contract as MCP tools and resources.
- The adapter does not copy use cases, permissions, routes, or validation rules.

### 1. Describe an action in the Muscles contract

In a real application this contract should come from `inspect_application(app)`
or `muscles inspect --json`. The important part is that the action is described
once by Muscles and then reused by MCP.

```python
contract = {
    "contract_version": "1",
    "framework": "Muscles",
    "app": "BookingApp",
    "actions": [
        {
            "name": "bookings.create",
            "description": "Create a booking request",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "guest_count": {"type": "integer"},
                },
                "required": ["title"],
            },
        }
    ],
    "routes": [
        {
            "name": "bookings.create",
            "path": "/bookings",
            "method": "POST",
        }
    ],
    "schemas": [
        {
            "name": "BookingCreate",
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "guest_count": {"type": "integer"},
            },
        }
    ],
    "rules": [
        {"name": "bookings.public_create"}
    ],
}
```

### 2. Connect MCP to the existing Muscles execution path

The Muscles application is the bridge. The preferred integration is a strategy
connected to the Muscles context. MCP reads the contract through
`inspect_application(app)` and executes tools through `ActionDispatcher`.

```python
from muscles_mcp import McpAdapter, McpRouter, McpStrategy

from muscles import ApplicationMeta, Context, register_action


class BookingApp(metaclass=ApplicationMeta):
    context = Context(McpStrategy)
    mcp = McpRouter(route_prefix="/api")


app = BookingApp()


register_action(
    app,
    name="bookings.create",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "guest_count": {"type": "integer"},
        },
        "required": ["title"],
    },
    handler=lambda payload, context: {
        "id": 1,
        "title": payload["title"],
        "guest_count": payload.get("guest_count", 1),
        "status": "created",
    },
)


# Alternative style for route-first registration (controller-like ergonomics)
public = app.mcp.server(name="public", route_prefix="/bookings", token="SIMSIM-PUBLIC")


@public.action(route="/create", name="bookings.create", description="Create a booking request")
def create_booking(payload, context):
    return {
        "id": 1,
        "title": payload["title"],
        "guest_count": payload.get("guest_count", 1),
        "status": "created",
    }


admin = app.mcp.server(name="admin", route_prefix="/admin")


@admin.action(route="/health", name="admin.health")
def admin_health(payload, context):
    return {"ok": True}


tools = app.context.execute(operation="list_tools", server="public", token="SIMSIM-PUBLIC")
admin_tools = app.context.execute(operation="list_tools", server="admin")
response = app.context.execute(
    operation="call_tool",
    server="public",
    token="SIMSIM-PUBLIC",
    name="bookings.create",
    arguments={"title": "Discovery call"},
)

# Compatibility facade for existing callers.
adapter = McpAdapter.from_application(app)
```

See [examples/booking_app.py](examples/booking_app.py) for a complete
application example that uses a Muscles `Model` as the action input schema.
MCP now normalizes Model-based schemas during execution automatically.
If you need a standalone schema builder, use `build_model_json_schema`.

### 2.5. One app for MCP, ASGI and WSGI

A single `App` instance can power MCP, ASGI and WSGI entrypoints.
Use `make_protocol_app(app, protocol)` to switch protocol handling in one place.
The same application context, registry, actions, routes, and validation logic stay
as the single source of truth.

### 3. Let an AI client discover available tools

```python
tools = app.context.execute(operation="list_tools")

assert tools == [
    {
        "name": "bookings.create",
        "description": "Create a booking request",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "guest_count": {"type": "integer"},
            },
            "required": ["title"],
        },
    }
]
```

An AI client should use this list instead of guessing which functions exist in
the codebase.

### 4. Expose Muscles metadata as MCP resources

```python
resources = app.context.execute(operation="list_resources")

assert {resource["uri"] for resource in resources} == {
    "muscles://app/inspect",
    "muscles://app/actions",
    "muscles://app/routes",
    "muscles://app/schemas",
    "muscles://app/rules",
}

inspect_resource = app.context.execute(operation="read_resource", uri="muscles://app/inspect")
actions_resource = app.context.execute(operation="read_resource", uri="muscles://app/actions")
```

These resources give an agent stable context before it edits or calls the app.
The agent can inspect routes, actions, schemas, and rules through one official
contract instead of scanning random Python files.

### 5. Call a Muscles action through MCP

```python
response = app.context.execute(
    operation="call_tool",
    name="bookings.create",
    arguments={"title": "Discovery call", "guest_count": 2},
)

assert response == {
    "content": [
        {
            "type": "json",
            "json": {
                "id": 1,
                "title": "Discovery call",
                "guest_count": 2,
                "status": "created",
            },
        }
    ]
}
```

The MCP adapter does not know how to create a booking. It delegates execution to
the Muscles dispatcher, where validation, rules and the use case live.

### 6. Validation and permission errors stay structured

If a required argument is missing, the adapter returns a machine-readable error:

```python
missing_title = adapter.call_tool("bookings.create", {"guest_count": 2})

assert missing_title == {
    "isError": True,
    "error": {
        "code": "invalid_params",
        "message": "'title' is a required property",
        "data": {"path": []},
    },
}
```

If the Muscles rules/security layer denies the action, the core dispatcher raises
`ActionPermissionDenied` and MCP maps it to a protocol error:

```python
from muscles import ActionPermissionDenied


def denied_handler(payload, context):
    raise ActionPermissionDenied(context.action.name, "Denied by Muscles rules")


register_action(app, name="bookings.create", handler=denied_handler)
secure_adapter = McpAdapter.from_application(app)
denied = secure_adapter.call_tool("bookings.create", {"title": "Call"})

assert denied == {
    "isError": True,
    "error": {
        "code": "permission_denied",
        "message": "Denied by Muscles rules",
        "data": None,
    },
}
```

This keeps MCP aligned with the framework: security decisions belong to Muscles,
while MCP only transports the structured result.

### 7. Build from a real Muscles application

When the app already supports `inspect_application(app)`, use
`McpAdapter.from_application(app)`:

```python
from muscles_mcp import McpAdapter

adapter = McpAdapter.from_application(app)

tools = adapter.list_tools()
inspect_resource = adapter.read_resource("muscles://app/inspect")
result = adapter.call_tool("bookings.create", {"title": "Call"})
```

`from_application()` delegates tool execution to `ActionDispatcher` with
`transport="mcp"`. The application model, rules, schemas and use cases stay in
Muscles.
