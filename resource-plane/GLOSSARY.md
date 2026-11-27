# Resource Plane

Application databases and object storage, their access credentials, and the interfaces for managing them. Shared terms, including Resource Plane Project, Resource Plane Console, and Resource Plane Management API, are defined in the [factory glossary](../GLOSSARY.md).

## Language

### Application resources

**Database**:
An isolated PostgreSQL database belonging to a Resource Plane Project, accessed through its dedicated Resource Role.
_Avoid_: Cluster, server

**Object Storage**:
An S3-compatible bucket belonging to a Resource Plane Project, with its own Storage Credentials.
_Avoid_: File share, volume

**Resource Role**:
A PostgreSQL login dedicated to a Database, with access restricted to that Database.

**Storage Credentials**:
The application connection details and access keys issued for one Object Storage bucket.

### Console features

**SQL Scratchpad**:
The Resource Plane Console's query editor for running SQL against provisioned Databases.
_Avoid_: Scratchpad (without SQL)

**Object Browser**:
The Resource Plane Console's file explorer for inspecting and managing the contents of provisioned Object Storage buckets.

### Management access

**Admin Token**:
The management credential authorizing access to the Resource Plane Management API.

**Resource Plane Console Credentials**:
The sign-in credentials for the Resource Plane Console, separate from application database and storage credentials.
_Avoid_: Control Plane Credentials, unqualified dashboard login

**Master Database Credentials**:
The internal administrative credentials for provisioning Databases and managing their Resource Roles.

**Storage Admin Credentials**:
The internal administrative credentials for provisioning Object Storage buckets and their bucket-scoped Storage Credentials.
