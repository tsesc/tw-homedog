## ADDED Requirements

### Requirement: List command registration
The system SHALL register a `/list` command handler in the Bot application. The /list command MUST be listed in the returning user welcome message.

#### Scenario: Returning user sees /list
- **WHEN** user sends `/start` and config already exists
- **THEN** Bot responds with welcome message listing available commands including /list

## MODIFIED Requirements

### Requirement: Manual pipeline trigger
The system SHALL provide a `/run` command to manually trigger the scrape → match → notify pipeline.

#### Scenario: Manual run
- **WHEN** user sends `/run`
- **THEN** Bot responds with "開始執行..." and runs the full pipeline
- **WHEN** pipeline completes with new unread matches
- **THEN** Bot sends summary: "完成！爬取 N 筆，新增 M 筆，有 K 筆未讀物件符合條件，使用 /list 查看"

#### Scenario: Manual run with no new matches
- **WHEN** user sends `/run` and pipeline completes with no unread matches
- **THEN** Bot sends summary: "完成！爬取 N 筆，新增 M 筆，目前沒有新的未讀物件"

#### Scenario: Run while already running
- **WHEN** user sends `/run` while pipeline is already executing
- **THEN** Bot responds with "Pipeline 正在執行中，請稍候"

### Requirement: Status display
The system SHALL provide a `/status` command showing current configuration summary and pipeline execution status.

#### Scenario: View status
- **WHEN** user sends `/status`
- **THEN** Bot responds with formatted message showing: current mode, region, districts, price range, size filter, keywords, schedule frequency, last run time, next run time, total listings in DB, unread matched count (replacing unnotified count)
