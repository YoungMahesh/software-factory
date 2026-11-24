# Docker Engine Auto-Management via Socket

The control plane directly communicates with the local Docker daemon via `/var/run/docker.sock` to detect, start, and monitor `neon-postgres` and `neon-seaweedfs` containers automatically. To accommodate both developer preferences and headless deployments, a standalone `docker-compose.yml` is also maintained for manual orchestration.
