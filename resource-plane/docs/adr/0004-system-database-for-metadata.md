# Metadata Storage in Managed PostgreSQL System Database

Control plane metadata (projects, database registries, S3 bucket metadata, and encrypted credentials) is stored in a dedicated `neon_control_plane` database on the managed PostgreSQL container. This avoids introducing SQLite or additional database engines into the tech stack and unifies migrations under Drizzle ORM, with the operational requirement that the core PostgreSQL container must be started before metadata queries can resolve.
