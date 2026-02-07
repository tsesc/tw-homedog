## ADDED Requirements

### Requirement: Dockerfile with Playwright support
The system SHALL provide a multi-stage Dockerfile using `ghcr.io/astral-sh/uv` base image. The runtime image MUST include Playwright chromium and its system dependencies.

#### Scenario: Docker build
- **WHEN** user runs `docker build -t tw-homedog .`
- **THEN** image builds successfully with all Python dependencies and Playwright chromium installed

#### Scenario: Container startup
- **WHEN** user runs `docker run tw-homedog`
- **THEN** Bot process starts and begins polling

### Requirement: Docker Compose configuration
The system SHALL provide a `docker-compose.yml` with volume mounts for data persistence and environment variable configuration.

#### Scenario: Docker compose up
- **WHEN** user runs `docker compose up -d`
- **THEN** container starts with data volume mounted at `/app/data` and logs at `/app/logs`

#### Scenario: Data persistence
- **WHEN** container is stopped and restarted
- **THEN** SQLite database and all config/listings data are preserved via volume mount

### Requirement: Environment variable configuration
The system SHALL read `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from environment variables. `LOG_LEVEL` environment variable MUST control logging level.

#### Scenario: Token from environment
- **WHEN** `TELEGRAM_BOT_TOKEN` is set in environment
- **THEN** system uses it as the bot token (overrides DB config if present)

#### Scenario: Log level from environment
- **WHEN** `LOG_LEVEL=DEBUG` is set
- **THEN** logging level is set to DEBUG on startup

#### Scenario: Missing required env vars
- **WHEN** `TELEGRAM_BOT_TOKEN` is not set and not in DB config
- **THEN** system exits with error "TELEGRAM_BOT_TOKEN is required"

### Requirement: Health check
The system SHALL log a heartbeat message at INFO level every schedule cycle to confirm the process is alive.

#### Scenario: Heartbeat logging
- **WHEN** scheduled pipeline job completes
- **THEN** system logs "Pipeline heartbeat: completed at {timestamp}, next run at {next_time}"
