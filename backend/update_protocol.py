REQUIRED_UPDATER_PROTOCOL = 2
MIN_UPDATER_PROTOCOL_LABEL = "io.ciphermoth.min-updater-protocol"
HEARTBEAT_MAX_AGE_SECONDS = 60
LEGACY_UPDATER_WINDOW_SECONDS = 3600
RECREATE_UPDATER_COMMAND = (
    "docker compose -f docker-compose.prod.yml --profile autoupdate pull updater && "
    "docker compose -f docker-compose.prod.yml --profile autoupdate up -d "
    "--no-deps updater"
)
