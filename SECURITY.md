# Security Policy

## Reporting a vulnerability

If you find a security issue in `mcp-drill` itself, please open a GitHub security advisory
(preferred) or a regular issue without sensitive exploit details, and we will follow up.

## Responsible use of reliability findings

`mcp-drill` can reveal fault-handling weaknesses in third-party MCP servers. When reporting
findings about servers you do not maintain, follow coordinated disclosure:

1. Report the concrete, reproducible issue to the server's maintainers first, with a fix or a
   minimal reproduction where possible.
2. Give maintainers reasonable time to respond before publishing aggregate results.
3. Publish grades and methodology, not gotchas — the goal is a more reliable ecosystem, not
   public shaming.

Never use `mcp-drill` to attack infrastructure you are not authorized to test.
