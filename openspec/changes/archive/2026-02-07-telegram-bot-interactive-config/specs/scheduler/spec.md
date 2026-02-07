## ADDED Requirements

### Requirement: Automatic pipeline scheduling
The system SHALL use `python-telegram-bot` JobQueue to run the pipeline at a configurable interval. The default interval MUST be 30 minutes.

#### Scenario: Default schedule
- **WHEN** Bot starts with no custom schedule configured
- **THEN** pipeline runs every 30 minutes automatically

#### Scenario: Custom interval
- **WHEN** user sets schedule interval to 60 minutes via `/settings`
- **THEN** pipeline runs every 60 minutes

### Requirement: Dynamic schedule adjustment
The system SHALL allow changing the schedule interval through the Bot without restarting. The new interval MUST take effect immediately.

#### Scenario: Change interval via settings
- **WHEN** user changes interval from 30 to 60 minutes in `/settings` → "排程"
- **THEN** existing scheduled job is removed and new job with 60-minute interval is created
- **THEN** Bot confirms "排程已更新：每 60 分鐘執行一次"

### Requirement: Pause and resume scheduling
The system SHALL provide `/pause` and `/resume` commands to control pipeline scheduling.

#### Scenario: Pause scheduling
- **WHEN** user sends `/pause`
- **THEN** scheduled pipeline job is paused and Bot confirms "已暫停自動執行"

#### Scenario: Resume scheduling
- **WHEN** user sends `/resume`
- **THEN** scheduled pipeline job is resumed and Bot confirms "已恢復自動執行，下次執行時間：{time}"

#### Scenario: Pause when already paused
- **WHEN** user sends `/pause` while already paused
- **THEN** Bot responds "已經處於暫停狀態"

### Requirement: Run tracking
The system SHALL track pipeline execution times in the database. Last run time and next run time MUST be queryable.

#### Scenario: After pipeline run
- **WHEN** pipeline completes (success or failure)
- **THEN** last_run_at timestamp and last_run_status are recorded in bot_config

#### Scenario: Query run status
- **WHEN** `/status` command is issued
- **THEN** displays last_run_at, last_run_status, and next_run_at
