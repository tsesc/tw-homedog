## ADDED Requirements

### Requirement: Configurable log level
The system SHALL support configurable log levels via environment variable `LOG_LEVEL`. The default MUST be `INFO` in production.

#### Scenario: Default log level
- **WHEN** no `LOG_LEVEL` environment variable is set
- **THEN** logging level is INFO

#### Scenario: Custom log level
- **WHEN** `LOG_LEVEL=DEBUG` is set
- **THEN** logging level is DEBUG and debug messages are visible

#### Scenario: Dynamic log level via Bot
- **WHEN** user sends `/loglevel DEBUG` via Telegram
- **THEN** logging level changes to DEBUG immediately without restart
- **THEN** Bot confirms "Log level 已更新為: DEBUG"

### Requirement: File and console logging
The system SHALL output logs to both console (stdout) and a rotating file. The file handler MUST use `RotatingFileHandler` with configurable max size and backup count.

#### Scenario: Dual output
- **WHEN** system generates a log message
- **THEN** message appears on both stdout and in log file at `logs/tw_homedog.log`

#### Scenario: Log rotation
- **WHEN** log file exceeds 10MB
- **THEN** file is rotated and up to 5 backup files are kept

### Requirement: Structured log format
The system SHALL use a consistent log format including timestamp, level, module name, and message.

#### Scenario: Log format
- **WHEN** a log message is generated
- **THEN** output format is `%(asctime)s [%(levelname)s] %(name)s: %(message)s` with ISO-8601 timestamp

### Requirement: Pipeline execution logging
The system SHALL log detailed pipeline execution information including start/end times, listing counts, and errors.

#### Scenario: Pipeline start
- **WHEN** pipeline starts executing
- **THEN** logs "Pipeline started" at INFO level

#### Scenario: Pipeline completion
- **WHEN** pipeline completes successfully
- **THEN** logs "Pipeline completed: scraped={N}, new={M}, matched={K}, notified={J}, duration={T}s" at INFO level

#### Scenario: Pipeline error
- **WHEN** pipeline encounters an error
- **THEN** logs the error with full stack trace at ERROR level and continues to next scheduled run
