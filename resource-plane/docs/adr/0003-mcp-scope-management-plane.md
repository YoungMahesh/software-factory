# MCP Scope Restricted to Management Plane

The Model Context Protocol (MCP) server provides AI agents with tools strictly for infrastructure lifecycle and credential management (creating, listing, and deleting databases and buckets, and reading connection credentials). It explicitly excludes raw SQL query execution and arbitrary S3 file uploads/downloads within the MCP server itself to maintain strong security boundaries and keep the MCP tool contracts focused.
