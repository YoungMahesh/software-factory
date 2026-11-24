# Strict Per-Database Role Isolation in PostgreSQL

Each provisioned database is paired with a distinct, randomly generated PostgreSQL user role and cryptographic password. The user is assigned ownership only over its allocated database, and connections to the system `neon_control_plane` database and other databases are revoked. The control plane retains master superuser credentials exclusively for administrative provisioning.
