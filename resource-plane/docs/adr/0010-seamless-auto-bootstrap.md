# Seamless Auto-Bootstrap on Launch

Upon server startup, the control plane automatically inspects Docker daemon connectivity via `/var/run/docker.sock`. If the `neon-postgres` or `neon-seaweedfs` containers are not running, it pulls images and starts them with designated volume mounts. Once PostgreSQL passes readiness probes, the bootstrapper creates the `neon_control_plane` database if absent and runs Drizzle migrations, enabling zero-config developer onboarding.
