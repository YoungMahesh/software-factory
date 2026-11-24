# Shared Container Topology for PostgreSQL and SeaweedFS

To support instant resource creation and maintain minimal CPU/memory overhead on local and host machines, the control plane runs a single shared PostgreSQL container and a single shared SeaweedFS container rather than provisioning a new Docker container per database or bucket. Individual databases are isolated through PostgreSQL roles and separate logical databases, and individual object storages are isolated through discrete S3 buckets with dedicated access keys.
