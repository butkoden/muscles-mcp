# MCP Projection

`muscles-mcp` exposes a Muscles application to MCP clients as a protocol
strategy. It does not define a separate business model, validation model,
permissions model, or action registry.

## Connection

The preferred integration point is a Muscles context:

```python
from muscles.core import ApplicationMeta, Context
from muscles_mcp import McpStrategy


class App(metaclass=ApplicationMeta):
    context = Context(McpStrategy)
```

`McpAdapter.from_application(app)` remains available as a compatibility facade
for existing callers, but it delegates to the same strategy/projection logic.

A complete user-application example is available in `examples/booking_app.py`.
It uses a Muscles `Model` as the action `input_schema` and calls the action
through `Context(McpStrategy)`.

## Discovery

MCP tools and resources are built from the Muscles inspect contract:

```python
tools = app.context.execute(operation="list_tools")
inspect_resource = app.context.execute(
    operation="read_resource",
    uri="muscles://app/inspect",
)
```

`inspect_application(app)` remains the source of truth.

## Tool Calls

Tool calls go back to Muscles core:

```python
response = app.context.execute(
    operation="call_tool",
    name="bookings.create",
    arguments={"title": "Call"},
)
```

Internally the strategy calls `ActionDispatcher(app).execute(...)` with
`transport="mcp"`. Validation, rules/security, and handler execution happen in
core.

## Contract Payload Example

You can pass a MCP request contract object directly:

```python
response = app.context.execute(
    request={
        "operation": "call_tool",
        "name": "bookings.create",
        "arguments": {"title": "Hello MCP", "guest_count": 2},
    }
)
```

The same shape is used for discovery:

```python
tools = app.context.execute(request={"operation": "list_tools"})
actions = app.context.execute(request={"operation": "read_resource", "uri": "muscles://app/actions"})
```

## Streaming

Stream-capable actions are discovered through `inspect_application(app)`.
When the core `ActionDispatcher` returns a `StreamResult`, the strategy projects
each `StreamEvent` into MCP JSON content with `event`, `data`, `id`, and
`metadata`. If the stream emits an error event, the MCP response gets
`isError=true`.

## MCP Schemas

MCP protocol message schemas live in `muscles_mcp.schema.mcp`. They inherit from
Muscles schema primitives, while keeping protocol-specific names:
`McpToolDescriptor`, `McpToolCallRequest`, `McpToolCallResult`,
`McpResourceDescriptor`, and `McpResourceReadResult`.

The MCP package avoids module and class names that collide with core names such
as `schema.py`, `model.py`, `response.py`, `Model`, `Schema`, or `Response`.

## Error Mapping

- `ActionNotFound` -> `not_found`;
- `ActionValidationError` -> `invalid_params`;
- `ActionPermissionDenied` -> `permission_denied`;
- `ActionExecutionError` -> `execution_error`.

## State

The strategy is scoped to the concrete application instance received from
Muscles `Context`. MCP should not share a mutable tool/action registry between
applications.
