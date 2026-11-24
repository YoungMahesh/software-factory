# Non-Destructive 8-Tool MCP Surface

The MCP server exposes a minimal, non-destructive surface of 8 tools: `list_projects`, `create_project`, `create_database`, `list_databases`, `get_database_credentials`, `create_object_storage`, `list_object_storages`, and `get_storage_credentials`. Deletion and password reset operations are intentionally omitted from agent tools to protect developer infrastructure against accidental truncation or drop cascades triggered by autonomous AI agents.
