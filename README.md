# Muscles MCP

Model Context Protocol adapter for Muscles.

This package should expose a Muscles application to AI tools through MCP without
copying application logic into the adapter.

## Concept Guardrails

- Muscles remains the source of truth for actions, schemas, rules, context, and
  permissions.
- MCP tools/resources must be generated from the Muscles application contract.
- The adapter must not invent its own routing, validation, auth, or business
  model.
- A use case implemented once in Muscles should become available through MCP
  without rewriting the use case.
- Machine-readable metadata is a product feature, not an internal detail.

## Initial Goal

Expose a minimal Muscles app as MCP tools and resources, backed by
`muscles inspect --json` compatible contract data.

## Current Stage (Issue #1)

Implemented MCP adapter baseline from Muscles inspect contract:

- `list_tools()` from contract `actions`;
- `list_resources()` for canonical MCP URIs:
  - `muscles://app/inspect`
  - `muscles://app/actions`
  - `muscles://app/routes`
  - `muscles://app/schemas`
  - `muscles://app/rules`
- `read_resource(uri)` returns stable JSON payload per resource;
- `call_tool()` delegates to Muscles action handler (no business-logic copy);
- tool input validation is derived from action `input_schema`;
- permission/rule denial is returned as structured MCP error.

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

The action handler is the bridge back into Muscles. In production code this
should call the same context/use case path used by HTTP, CLI, JSON-RPC, or other
adapters.

```python
from muscles_mcp import McpAdapter


class BookingContext:
    def execute(self, action_name: str, **payload):
        if action_name == "bookings.create":
            return {
                "id": 1,
                "title": payload["title"],
                "guest_count": payload.get("guest_count", 1),
                "status": "created",
            }
        raise LookupError(action_name)


context = BookingContext()
adapter = McpAdapter(
    inspect_contract=contract,
    action_handler=lambda name, args: context.execute(name, **args),
)
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

The MCP adapter does not know how to create a booking. It only validates the
input shape from the Muscles contract and delegates execution to the Muscles
application path.

### 6. Validation and permission errors stay structured

If a required argument is missing, the adapter returns a machine-readable error:

```python
missing_title = adapter.call_tool("bookings.create", {"guest_count": 2})

assert missing_title == {
    "isError": True,
    "error": {
        "code": "invalid_params",
        "message": "Missing required argument: title",
        "data": None,
    },
}
```

If the Muscles rules/security layer denies the action, return a `PermissionError`
from the action handler:

```python
def denied_handler(name, args):
    raise PermissionError("Denied by Muscles rules")


secure_adapter = McpAdapter(contract, denied_handler)
denied = secure_adapter.call_tool("bookings.create", {"title": "Call"})

assert denied == {
    "isError": True,
    "error": {
        "code": "permission_denied",
        "message": "Denied by Muscles rules",
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

By default, `from_application()` delegates tool execution to:

```python
app.context.execute(action_name, **arguments)
```

If an application needs a custom dispatch policy, pass `action_handler`:

```python
adapter = McpAdapter.from_application(
    app,
    action_handler=lambda name, args: app.context.execute("mcp", name, **args),
)
```

The rule is the same: MCP is only a protocol adapter. The application model,
rules, schemas, and use cases stay in Muscles.
