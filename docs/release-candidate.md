# MCP RC checklist

The MCP RC must pass the client smoke path:

```bash
PYTHONPATH=../muscles/src:src python -m pytest -q
python -m build --wheel --sdist
```

Verify initialize, tools/resources discovery, tool calls, permission profiles,
resource redaction and clean installation. Tools and resources come from the
core inspection contract; tokens, prompts and credentials never leave the
application boundary.
