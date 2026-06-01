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

Implemented minimal MCP adapter from Muscles inspect contract:

- `list_tools()` from `actions` section;
- `list_resources()` from `schemas` section;
- `call_tool()` delegates to Muscles action handler.

### Run tests

```bash
python -m pytest -q
```
