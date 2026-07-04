# MCP Projection

`muscles-mcp` открывает Muscles application для MCP clients как protocol
strategy. Он не определяет отдельную business model, validation model,
permissions model или action registry.

## Подключение

Основной способ подключения - Muscles context:

```python
from muscles.core import ApplicationMeta, Context
from muscles_mcp import McpStrategy
from muscles.asgi import AsgiStrategy


class App(metaclass=ApplicationMeta):
    # Контекст MCP может ссылаться на entrypoint-контекст (например asgi).
    asgi = Context(AsgiStrategy)
    mcp = Context(McpStrategy, transport=asgi)
```

Для сценария с несколькими профилями создаём отдельные entrypoint-контексты и
привязываем к ним MCP-контексты напрямую:

```python
class App(metaclass=ApplicationMeta):
    asgi_public = Context(AsgiStrategy, params={"profile": "public"})
    asgi_admin = Context(AsgiStrategy, params={"profile": "admin"})

    mcp_public = Context(McpStrategy, transport=asgi_public, params={"mcp_profile": "public"})
    mcp_admin = Context(McpStrategy, transport=asgi_admin, params={"mcp_profile": "admin"})
```

`McpAdapter.from_application(app)` сохранен как совместимый facade для старого
кода, но внутри использует ту же strategy/protocol логику.

`transport` в `Context(McpStrategy, transport=...)` теперь обычно ссылается на entrypoint:
- `transport=asgi` / `transport=wsgi` / `transport=cli` для прямого протокольного привязки;
- `transport=<other_context>` или `transport="asgi_public"` / `transport="asgi_admin"` для привязки к конкретному entrypoint-контексту.

Важно: для MCP-контекста `router` больше не нужен: transport уже указывает на entrypoint.
Маршрутизация (`route`/`route_prefix`/`servers`) задается в entrypoint-контексте или в `metadata["mcp"]` при регистрации action, а MCP-контекст хранит только выбор стратегии/профиля.

Пример без `router` в параметрах MCP-контекста:

```python
Context(McpStrategy, transport=asgi_public, params={"mcp_profile": "public"})
```

Полный пример пользовательского приложения есть в
`examples/booking_app.py`. В нем action использует Muscles `Model` как
`input_schema`, а MCP вызывает этот action через MCP-контекст.

## Discovery

MCP tools и resources строятся из Muscles inspect contract:

```python
tools = app.mcp.execute(operation="list_tools")
inspect_resource = app.mcp.execute(
    operation="read_resource",
    uri="muscles://app/inspect",
)
```

`inspect_application(app)` остается источником истины.

## Standalone JSON-RPC server

`McpStrategy` остается основным способом проецировать Muscles application в MCP.
Для сервисов, которые еще не описаны как Muscles application, или для продуктов
с собственной бизнес-регистратурой, `McpServer` дает только MCP-протокольную
обвязку.

```python
from muscles_mcp import McpResource, McpServer, McpTool, mcp_list_schema


server = McpServer(
    name="assetforge-mcp",
    version="1.0.0",
    instructions="Use tools with the connected user's permissions.",
    tools=[
        McpTool(
            name="workspaces.list",
            description="List workspaces.",
            input_schema={"type": "object", "properties": {}},
            output_schema=mcp_list_schema(),
            read_only=True,
        )
    ],
    resources=[
        McpResource(
            uri="assetforge://catalog",
            name="catalog",
            description="Service catalog.",
        )
    ],
    call_tool=lambda name, arguments, context: [{"uid": "workspace-full-uid"}],
    read_resource=lambda uri, arguments, context: {"uri": uri},
)
```

`handle_jsonrpc(...)` поддерживает:

- `initialize`;
- `ping`;
- `tools/list`;
- `tools/call`;
- `resources/list`;
- `resources/read`;
- `resources/templates/list`;
- `prompts/list`;
- JSON-RPC batch requests и notifications.

Tool descriptors используют MCP protocol names: `inputSchema`, `outputSchema`
и `annotations` с `readOnlyHint` и `destructiveHint`.

Tool call всегда возвращает `structuredContent` как object:

- `dict` возвращается без изменений;
- `list` превращается в `{"items": [...], "count": N}`;
- primitive values и `None` превращаются в `{"value": ...}`.

`content[0].text` сериализует тот же object как JSON text.

Бизнес-логика остается вне `McpServer`: permissions, token validation,
application audit, CRUD и mapping public payload должны жить в callbacks
приложения.

## Tool calls

Tool calls возвращаются в Muscles core:

```python
response = app.mcp.execute(
    operation="call_tool",
    name="bookings.create",
    arguments={"title": "Call"},
)
```

Внутри strategy вызывает `ActionDispatcher(app).execute(...)` с
`transport="mcp"`. Валидация, rules/security и handler execution происходят в
core.

`McpStrategy` — это protocol codec. Он отвечает за формат MCP-запросов и ответов
(инструменты/ресурсы/ошибки), но не за сетевой транспорт.
Транспортный уровень обеспечивают внешние entrypoint-обертки:
- `make_mcp_asgi_app` — MCP поверх ASGI HTTP;
- `make_mcp_wsgi_app` — MCP поверх WSGI HTTP;
- `make_mcp_cli_command` — MCP через CLI/stdio-подобный поток ввода-вывода.

## Пример через контрактный payload

Можно передавать MCP-запрос как единый payload:

```python
response = app.mcp.execute(
    request={
        "operation": "call_tool",
        "name": "bookings.create",
        "arguments": {"title": "Hello MCP", "guest_count": 2},
    }
)
```

То же самое для discovery:

```python
tools = app.mcp.execute(request={"operation": "list_tools"})
actions = app.mcp.execute(request={"operation": "read_resource", "uri": "muscles://app/actions"})
```

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

Standalone JSON-RPC errors маппятся в числовые protocol codes:

- invalid request -> `-32600`;
- invalid params -> `-32602`;
- method, tool или resource not found -> `-32601`;
- access denied -> `-32001`;
- not found -> `-32004`;
- internal error -> `-32000`.

## OAuth и DCR discovery

`oauth_protected_resource_metadata(...)` и
`oauth_authorization_server_metadata(...)` собирают ChatGPT-compatible discovery
metadata для:

- `/.well-known/oauth-protected-resource`;
- `/.well-known/oauth-protected-resource/mcp`;
- `/.well-known/oauth-authorization-server`;
- `/.well-known/oauth-authorization-server/mcp`.

`register_mcp_routes(...)` регистрирует discovery routes, `/oauth/register`,
`/oauth/authorize`, `/oauth/token` и MCP POST transport route. Helper не хранит
OAuth clients, authorization codes или access tokens. Для реальной выдачи
credentials нужно передать `McpOAuthProvider` из host application.

## State

Strategy работает с конкретным application instance, полученным из Muscles
`Context`. MCP не должен шарить mutable tool/action registry между
приложениями.
