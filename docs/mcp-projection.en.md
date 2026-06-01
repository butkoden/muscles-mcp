# MCP Projection

`muscles-mcp` exposes a Muscles application to MCP clients. It does not define a
separate business model, validation model, permissions model, or action registry.

## Discovery

MCP tools and resources are built from the Muscles inspect contract:

```python
adapter = McpAdapter.from_application(app)
tools = adapter.list_tools()
inspect_resource = adapter.read_resource("muscles://app/inspect")
```

`inspect_application(app)` remains the source of truth.

## Tool Calls

Tool calls go back to Muscles core:

```python
response = adapter.call_tool("bookings.create", {"title": "Call"})
```

Internally the adapter calls `ActionDispatcher(app).execute(...)` with
`transport="mcp"`. Validation, rules/security, and handler execution happen in
core.

## Error Mapping

- `ActionNotFound` -> `not_found`;
- `ActionValidationError` -> `invalid_params`;
- `ActionPermissionDenied` -> `permission_denied`;
- `ActionExecutionError` -> `execution_error`.

## State

The adapter is scoped to a concrete application instance. It should not share a
mutable tool/action registry between applications.
