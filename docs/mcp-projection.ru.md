# MCP Projection

`muscles-mcp` открывает Muscles application для MCP clients как protocol
strategy. Он не определяет отдельную business model, validation model,
permissions model или action registry.

## Подключение

Основной способ подключения - Muscles context:

```python
from muscles.core import ApplicationMeta, Context
from muscles_mcp import McpStrategy


class App(metaclass=ApplicationMeta):
    context = Context(McpStrategy)
```

`McpAdapter.from_application(app)` сохранен как совместимый facade для старого
кода, но внутри использует ту же strategy/projection логику.

Полный пример пользовательского приложения есть в
`examples/booking_app.py`. В нем action использует Muscles `Model` как
`input_schema`, а MCP вызывает этот action через `Context(McpStrategy)`.

## Discovery

MCP tools и resources строятся из Muscles inspect contract:

```python
tools = app.context.execute(operation="list_tools")
inspect_resource = app.context.execute(
    operation="read_resource",
    uri="muscles://app/inspect",
)
```

`inspect_application(app)` остается источником истины.

## Tool calls

Tool calls возвращаются в Muscles core:

```python
response = app.context.execute(
    operation="call_tool",
    name="bookings.create",
    arguments={"title": "Call"},
)
```

Внутри strategy вызывает `ActionDispatcher(app).execute(...)` с
`transport="mcp"`. Валидация, rules/security и handler execution происходят в
core.

## Streaming

Stream-capable actions обнаруживаются через `inspect_application(app)`.
Если core `ActionDispatcher` возвращает `StreamResult`, strategy проецирует
каждый `StreamEvent` в MCP JSON content с полями `event`, `data`, `id` и
`metadata`. Если stream выдает error event, MCP response получает
`isError=true`.

## MCP-схемы

Схемы MCP protocol messages находятся в `muscles_mcp.schema.mcp`. Они
наследуются от Muscles schema primitives, но названы protocol-specific:
`McpToolDescriptor`, `McpToolCallRequest`, `McpToolCallResult`,
`McpResourceDescriptor`, `McpResourceReadResult`.

В пакете MCP не используются конфликтующие с core имена модулей и классов вроде
`schema.py`, `model.py`, `response.py`, `Model`, `Schema` или `Response`.

## Error mapping

- `ActionNotFound` -> `not_found`;
- `ActionValidationError` -> `invalid_params`;
- `ActionPermissionDenied` -> `permission_denied`;
- `ActionExecutionError` -> `execution_error`.

## State

Strategy работает с конкретным application instance, полученным из Muscles
`Context`. MCP не должен шарить mutable tool/action registry между
приложениями.
