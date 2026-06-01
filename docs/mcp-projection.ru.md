# MCP Projection

`muscles-mcp` открывает Muscles application для MCP clients. Он не определяет
отдельную business model, validation model, permissions model или action
registry.

## Discovery

MCP tools и resources строятся из Muscles inspect contract:

```python
adapter = McpAdapter.from_application(app)
tools = adapter.list_tools()
inspect_resource = adapter.read_resource("muscles://app/inspect")
```

`inspect_application(app)` остается источником истины.

## Tool calls

Tool calls возвращаются в Muscles core:

```python
response = adapter.call_tool("bookings.create", {"title": "Call"})
```

Внутри adapter вызывает `ActionDispatcher(app).execute(...)` с
`transport="mcp"`. Валидация, rules/security и handler execution происходят в
core.

## Error mapping

- `ActionNotFound` -> `not_found`;
- `ActionValidationError` -> `invalid_params`;
- `ActionPermissionDenied` -> `permission_denied`;
- `ActionExecutionError` -> `execution_error`.

## State

Adapter привязан к конкретному application instance. Он не должен шарить mutable
tool/action registry между приложениями.
