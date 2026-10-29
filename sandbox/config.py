"""Configuration constants and defaults for Modal sandbox execution."""

# Modal's default timeout for Sandbox.create is 300s (5 minutes) if omitted; max allowed is 24 hours.
TIMEOUT_SECS = 22 * 60 * 60  # 22 hours
IDLE_TIMEOUT_SECS = 4 * 60 * 60  # 4 hours
DEFAULT_ORG = "sFactory0"

DEFAULT_WEB_PORT = 3000
DEFAULT_OPENCODE_PORT = 4096
DEFAULT_METRO_PORT = 8081
DEFAULT_T3_PORT = 3775
