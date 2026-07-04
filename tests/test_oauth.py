from muscles_mcp import (
    McpServer,
    oauth_authorization_server_metadata,
    oauth_protected_resource_metadata,
    register_mcp_routes,
)


class _Routes:
    def __init__(self):
        self.handlers = {}

    def init(self, path, **options):
        def decorator(handler):
            self.handlers[(path, options.get("method", "GET"))] = handler
            return handler

        return decorator


def test_mcp_oauth_metadata_urls_for_chatgpt_compatible_discovery():
    protected = oauth_protected_resource_metadata(
        "https://assetforge.butko.info",
        resource_path="/mcp",
        scope="assetforge",
    )
    authorization = oauth_authorization_server_metadata(
        "https://assetforge.butko.info/",
        scope="assetforge",
    )

    assert protected == {
        "resource": "https://assetforge.butko.info/mcp",
        "authorization_servers": ["https://assetforge.butko.info"],
        "scopes_supported": ["assetforge"],
        "resource_documentation": "https://assetforge.butko.info/app",
        "bearer_methods_supported": ["header"],
    }
    assert authorization["issuer"] == "https://assetforge.butko.info"
    assert authorization["authorization_endpoint"] == "https://assetforge.butko.info/oauth/authorize"
    assert authorization["token_endpoint"] == "https://assetforge.butko.info/oauth/token"
    assert authorization["registration_endpoint"] == "https://assetforge.butko.info/oauth/register"
    assert authorization["token_endpoint_auth_methods_supported"] == [
        "none",
        "client_secret_post",
        "client_secret_basic",
    ]


def test_register_mcp_routes_adds_discovery_and_transport_handlers():
    routes = _Routes()
    server = McpServer(name="assetforge-mcp", version="1.0.0")

    register_mcp_routes(
        routes,
        path="/mcp",
        server=server,
        base_url=lambda request: "https://assetforge.butko.info",
    )

    protected = routes.handlers[("/.well-known/oauth-protected-resource", "GET")](None)
    protected_for_mcp = routes.handlers[("/.well-known/oauth-protected-resource/mcp", "GET")](None)
    authorization = routes.handlers[("/.well-known/oauth-authorization-server", "GET")](None)
    authorization_for_mcp = routes.handlers[("/.well-known/oauth-authorization-server/mcp", "GET")](None)
    get_transport = routes.handlers[("/mcp", "GET")](None)

    assert protected.body["resource"] == "https://assetforge.butko.info/mcp"
    assert protected_for_mcp.body == protected.body
    assert authorization.body["issuer"] == "https://assetforge.butko.info"
    assert authorization_for_mcp.body == authorization.body
    assert get_transport.status == 405
    assert ("Allow", "POST") in get_transport.headers
