# DB Host Control Plane

A developer-focused local cloud console and MCP server for provisioning isolated PostgreSQL databases and S3-compatible object storages backed by Docker.

## Language

**App Workspace**:
The core user interface and web application (`apps/web`), built with Next.js 16 App Router, React 19, and Tailwind CSS v4.

**Design System Theme**:
The centralized tokens package (`@repo/theme`) providing colors, typography, radii, and Tailwind presets.

**Project**:
A logical workspace grouping associated PostgreSQL databases and S3 object storage buckets for an application.
_Avoid_: Workspace, tenant, organization, namespace

**Database**:
A logically isolated PostgreSQL database provisioned on the shared PostgreSQL container, assigned a unique user, password, and restricted permissions.
_Avoid_: Cluster, instance, server

**Object Storage**:
An S3-compatible storage bucket provisioned on the shared SeaweedFS container, accompanied by dedicated access credentials.
_Avoid_: Blob store, file share, volume

**Connection String**:
The standard URI containing host, port, username, password, database name, and transport encryption parameters for client applications to connect directly to PostgreSQL.
_Avoid_: DSN, connection URL, db link

**CA Certificate**:
The root certificate authority file distributed to remote client applications to verify the PostgreSQL server's identity during encrypted connections.
_Avoid_: Root key, SSL secret, trust token

**Public Host**:
The externally reachable domain name or IP address configured for remote client applications to connect to provisioned databases.
_Avoid_: External IP, public bind, outer host

**Storage Credentials**:
The S3 configuration bundle (endpoint URL, bucket name, access key ID, and secret access key) supplied to external apps for object storage operations.
_Avoid_: S3 keys, auth token

**Control Plane**:
The dashboard interface and server actions / route handlers responsible for managing projects, credentials, and container lifecycles.
_Avoid_: Admin portal, management console

**MCP Server**:
The Model Context Protocol endpoint exposing management-plane tools to AI agents for provisioning databases and buckets and inspecting credentials.
_Avoid_: Agent gateway, AI proxy

**System Database**:
The internal `db_host_control_plane` (or `neon_control_plane`) database hosted on the managed PostgreSQL container where project metadata, resource definitions, and generated credentials are stored.
_Avoid_: Metadata store, state db, config store

**SQL Scratchpad**:
The in-dashboard SQL query editor and runner allowing developers to execute queries against their provisioned databases without leaving the browser.
_Avoid_: SQL runner, query console, workbench

**Object Browser**:
The in-dashboard file explorer allowing developers to view, upload, and inspect files stored in their provisioned S3 buckets.
_Avoid_: File manager, bucket explorer, s3 viewer

**Admin Token**:
A secret authentication token configured in the environment or settings that AI agents must provide to authorize MCP operations.
_Avoid_: API secret, session key, auth password

**Resource Role**:
A dedicated PostgreSQL user account generated for a specific database with ownership grants restricted strictly to that database.
_Avoid_: Database user, project login, tenant account

**Auto-Bootstrapper**:
The automated control-plane initialization service that detects Docker state, launches core containers, creates the system database, and runs migrations.
_Avoid_: Startup script, init wizard, seeder

**Data Directory**:
The local project-level directory (`./.data/`) used for persistent volume mounts storing PostgreSQL data clusters and SeaweedFS chunks.
_Avoid_: Storage volume, data mount, docker store

**Bucket IAM Policy**:
The configuration specifying an isolated access key ID and secret access key restricted exclusively to actions on a single target bucket.
_Avoid_: Bucket policy, s3 permission, user key

**MCP Tool Suite**:
The non-destructive set of 8 MCP tools (`list_projects`, `create_project`, `create_database`, `list_databases`, `get_database_credentials`, `create_object_storage`, `list_object_storages`, `get_storage_credentials`) exposed to AI agents.
_Avoid_: Agent tools, MCP schema, toolset

**Control Plane Credentials**:
The HTTP Basic Authentication username and password configured strictly in the environment (`.env.local`) required to access the control plane dashboard and server functions, independent of the system database and distinct from individual database Resource Roles or S3 Storage Credentials.
_Avoid_: Dashboard login, admin password, site auth

**Master Database Credentials**:
The PostgreSQL superuser username and password configured strictly in the environment (`.env.local`) used by the Auto-Bootstrapper and internal services to provision Databases and manage Resource Roles.
_Avoid_: Superuser password, root db login, postgres password

**Storage Admin Credentials**:
The root S3 access key and secret key configured strictly in the environment (`.env.local`) used by internal services to provision Object Storages and configure Bucket IAM Policies on SeaweedFS.
_Avoid_: S3 root keys, seaweed admin password, global storage token
