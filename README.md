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

## Current Stage (Issue #4)

Implemented MCP projection from Muscles inspect contract:

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

### Run tests

```bash
python -m pytest -q
```

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

The Muscles application is the bridge. MCP receives the app, reads its contract
through `inspect_application(app)`, and executes tools through
`ActionDispatcher`.

```python
from muscles_mcp import McpAdapter

from muscles import ApplicationMeta, Context, register_action


class BookingApp(metaclass=ApplicationMeta):
    context = Context(MyStrategy, {})


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


adapter = McpAdapter.from_application(app)
```

### 3. Let an AI client discover available tools

```python
tools = adapter.list_tools()

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
resources = adapter.list_resources()

assert {resource["uri"] for resource in resources} == {
    "muscles://app/inspect",
    "muscles://app/actions",
    "muscles://app/routes",
    "muscles://app/schemas",
    "muscles://app/rules",
}

inspect_resource = adapter.read_resource("muscles://app/inspect")
actions_resource = adapter.read_resource("muscles://app/actions")
```

These resources give an agent stable context before it edits or calls the app.
The agent can inspect routes, actions, schemas, and rules through one official
contract instead of scanning random Python files.

### 5. Call a Muscles action through MCP

```python
response = adapter.call_tool(
    "bookings.create",
    {"title": "Discovery call", "guest_count": 2},
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
