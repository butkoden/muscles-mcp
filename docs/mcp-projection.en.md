# MCP Projection

`muscles-mcp` exposes a Muscles application to MCP clients as a protocol
strategy. It does not define a separate business model, validation model,
permissions model, or action registry.

## Connection

The preferred integration point is a Muscles context:

```python
from muscles.core import ApplicationMeta, Context
from muscles_mcp import McpStrategy
from muscles.asgi import AsgiStrategy


class App(metaclass=ApplicationMeta):
    asgi = Context(AsgiStrategy)
    mcp = Context(McpStrategy, transport=asgi)
```

For multi-profile deployments you can create several entrypoint contexts and bind MCP contexts to them directly:

```python
class App(metaclass=ApplicationMeta):
    asgi_public = Context(AsgiStrategy, params={"profile": "public"})
    asgi_admin = Context(AsgiStrategy, params={"profile": "admin"})

    mcp_public = Context(McpStrategy, transport=asgi_public, params={"mcp_profile": "public"})
    mcp_admin = Context(McpStrategy, transport=asgi_admin, params={"mcp_profile": "admin"})
```

`McpAdapter.from_application(app)` remains available as a compatibility facade
for existing callers, but it delegates to the same strategy/projection logic.

`transport` in MCP context declarations points to where MCP is attached:
- direct protocol label (`"mcp"`, `"mcp-public"`, etc.);
- entrypoint context object (`transport=asgi`),
- context name string (`transport="asgi_public"`, `transport="asgi_admin"`).

As a result, MCP context no longer needs `router`/`route` in `params`.
The entrypoint context already carries the transport boundary.
Keep route metadata (`route`, `route_prefix`, server visibility) on the
entrypoint contexts and/or `metadata["mcp"]` on action registration, and use MCP context params
for strategy/profile metadata only.

Example without `router` in MCP params:

```python
Context(McpStrategy, transport=asgi_public, params={"mcp_profile": "public"})
```

A complete user-application example is available in `examples/booking_app.py`.
It uses a Muscles `Model` as the action `input_schema` and calls the action
through an MCP context.

## Discovery

MCP tools and resources are built from the Muscles inspect contract:

```python
tools = app.mcp.execute(operation="list_tools")
inspect_resource = app.mcp.execute(
    operation="read_resource",
    uri="muscles://app/inspect",
)
```

`inspect_application(app)` remains the source of truth.

## Standalone JSON-RPC Server

`McpStrategy` is the preferred Muscles projection. For services that are not yet
modeled as a Muscles application, or for existing products with their own
business registry, `McpServer` provides only the MCP protocol shell.

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

`handle_jsonrpc(...)` supports:

- `initialize`;
- `ping`;
- `tools/list`;
- `tools/call`;
- `resources/list`;
- `resources/read`;
- `resources/templates/list`;
- `prompts/list`;
- JSON-RPC batch requests and notifications.

Tool descriptors use MCP protocol names: `inputSchema`, `outputSchema`, and
`annotations` with `readOnlyHint` and `destructiveHint`.

Tool call results always contain object-shaped `structuredContent`:

- dictionaries are returned unchanged;
- lists become `{"items": [...], "count": N}`;
- primitives and `None` become `{"value": ...}`.

`content[0].text` serializes the same object as JSON text.

Business logic stays outside `McpServer`: permissions, token validation,
application audit, CRUD, and public payload mapping must live in the host
application callbacks.

## Tool Calls

Tool calls go back to Muscles core:

```python
response = app.mcp.execute(
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
response = app.mcp.execute(
    request={
        "operation": "call_tool",
        "name": "bookings.create",
        "arguments": {"title": "Hello MCP", "guest_count": 2},
    }
)
```

The same shape is used for discovery:

```python
tools = app.mcp.execute(request={"operation": "list_tools"})
actions = app.mcp.execute(request={"operation": "read_resource", "uri": "muscles://app/actions"})
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

Standalone JSON-RPC errors are mapped to protocol numeric codes:

- invalid request -> `-32600`;
- invalid params -> `-32602`;
- method, tool, or resource not found -> `-32601`;
- access denied -> `-32001`;
- not found -> `-32004`;
- internal error -> `-32000`.

## OAuth and DCR Discovery

`oauth_protected_resource_metadata(...)` and
`oauth_authorization_server_metadata(...)` build ChatGPT-compatible discovery
metadata for:

- `/.well-known/oauth-protected-resource`;
- `/.well-known/oauth-protected-resource/mcp`;
- `/.well-known/oauth-authorization-server`;
- `/.well-known/oauth-authorization-server/mcp`.

`register_mcp_routes(...)` registers discovery routes, `/oauth/register`,
`/oauth/authorize`, `/oauth/token`, and the MCP POST transport route. The helper
does not store OAuth clients, authorization codes, or access tokens. Pass an
`McpOAuthProvider` implementation from the host application when those endpoints
need to issue real credentials.

## State

The strategy is scoped to the concrete application instance received from
Muscles `Context`. MCP should not share a mutable tool/action registry between
applications.
