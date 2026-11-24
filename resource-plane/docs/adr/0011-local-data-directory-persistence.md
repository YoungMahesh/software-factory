# Local Project Data Directory Persistence

Persistent storage for PostgreSQL database clusters and SeaweedFS volume chunks is bound to a local `.data/` directory (`.data/postgres` and `.data/seaweedfs`) located at the repository root. This directory is excluded from git version control, making backups, inspections, and clean resets straightforward for developers without having to manage opaque Docker named volumes.
