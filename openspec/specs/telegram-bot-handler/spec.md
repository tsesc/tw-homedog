## ADDED Requirements

### Requirement: Bot startup and initialization
The system SHALL start a Telegram Bot long-polling process as the default entry point. The Bot MUST validate the bot token on startup and report errors clearly if invalid.

#### Scenario: Successful bot startup
- **WHEN** user runs `python -m tw_homedog` without `--cli` flag
- **THEN** the system starts Telegram Bot polling and logs "Bot started"

#### Scenario: Invalid bot token
- **WHEN** bot token is missing or invalid
- **THEN** the system logs an error with "Invalid bot token" and exits with code 1

### Requirement: Start command with guided setup
The system SHALL provide a `/start` command that initiates a guided setup conversation if no config exists, or shows a welcome message with available commands if config is already present.

#### Scenario: First-time setup
- **WHEN** user sends `/start` and no config exists in DB
- **THEN** Bot responds with welcome message and starts guided setup flow asking for mode (buy/rent), region, districts, price range, and optional filters in sequence using inline keyboards

#### Scenario: Returning user
- **WHEN** user sends `/start` and config already exists
- **THEN** Bot responds with welcome message listing available commands: /settings, /status, /run, /pause, /resume

### Requirement: Settings management via inline keyboard
The system SHALL provide a `/settings` command that displays all configurable parameters as inline keyboard buttons. Each parameter MUST be editable through the Bot conversation. The keyword settings MUST use an inline keyboard panel showing current keywords as deletable buttons, with action buttons for adding include/exclude keywords, clearing all, and confirming.

#### Scenario: View settings menu
- **WHEN** user sends `/settings`
- **THEN** Bot displays inline keyboard with buttons: 模式(Mode), 地區(Region), 區域(Districts), 價格(Price), 坪數(Size), 關鍵字(Keywords), 排程(Schedule), 通知(Notifications)

#### Scenario: Change search mode
- **WHEN** user taps "模式" button
- **THEN** Bot shows inline keyboard with "買房(Buy)" and "租房(Rent)" options
- **WHEN** user selects one
- **THEN** system updates mode in DB and confirms with "已更新搜尋模式為: 買房"

#### Scenario: Change districts
- **WHEN** user taps "區域" button
- **THEN** Bot shows inline keyboard with all districts for current region, pre-checked districts have ✅ prefix
- **WHEN** user taps a district to toggle, then taps "確認" button
- **THEN** system updates districts in DB and confirms with selected district list

#### Scenario: Change price range
- **WHEN** user taps "價格" button
- **THEN** Bot asks user to input price range in format "min-max" (e.g., "1000-2000")
- **WHEN** user inputs valid range
- **THEN** system updates price_min and price_max in DB and confirms

#### Scenario: Invalid price input
- **WHEN** user inputs invalid price format
- **THEN** Bot responds with error message and example of correct format, allowing retry

#### Scenario: Enter keyword settings
- **WHEN** user taps "關鍵字" button
- **THEN** Bot displays keyword panel with: current include keywords as "包含: {keyword}" buttons, current exclude keywords as "排除: {keyword}" buttons, and action row with "➕ 包含", "➖ 排除", "🗑 清除", "✅ 完成" buttons
- **WHEN** no keywords exist
- **THEN** Bot displays empty state message "尚無關鍵字" with only "➕ 包含", "➖ 排除", "✅ 完成" buttons

#### Scenario: Delete a keyword by tapping
- **WHEN** user taps an existing keyword button (include or exclude)
- **THEN** system removes that keyword from the corresponding list in DB
- **THEN** Bot refreshes the keyword panel with updated state

#### Scenario: Add include keyword
- **WHEN** user taps "➕ 包含" button
- **THEN** Bot sends message "請輸入要包含的關鍵字："
- **WHEN** user inputs a keyword text
- **THEN** system adds the keyword to include list in DB and refreshes the keyword panel

#### Scenario: Add exclude keyword
- **WHEN** user taps "➖ 排除" button
- **THEN** Bot sends message "請輸入要排除的關鍵字："
- **WHEN** user inputs a keyword text
- **THEN** system adds the keyword to exclude list in DB and refreshes the keyword panel

#### Scenario: Add duplicate keyword
- **WHEN** user inputs a keyword that already exists in the target list
- **THEN** Bot responds "此關鍵字已存在" and refreshes the keyword panel without modification

#### Scenario: Clear all keywords
- **WHEN** user taps "🗑 清除" button
- **THEN** system removes all include and exclude keywords from DB and refreshes the keyword panel showing empty state

#### Scenario: Finish keyword settings
- **WHEN** user taps "✅ 完成" button
- **THEN** Bot confirms "關鍵字設定完成" and exits keyword settings conversation state

### Requirement: Status display
The system SHALL provide a `/status` command showing current configuration summary and pipeline execution status.

#### Scenario: View status
- **WHEN** user sends `/status`
- **THEN** Bot responds with formatted message showing: current mode, region, districts, price range, size filter, keywords, schedule frequency, last run time, next run time, total listings in DB, unread matched count (replacing unnotified count)

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

### Requirement: List command registration
The system SHALL register a `/list` command handler in the Bot application. The /list command MUST be listed in the returning user welcome message.

#### Scenario: Returning user sees /list
- **WHEN** user sends `/start` and config already exists
- **THEN** Bot responds with welcome message listing available commands including /list

### Requirement: Chat ID authorization
The system SHALL only respond to messages from the configured chat_id. Messages from other users MUST be ignored.

#### Scenario: Authorized user
- **WHEN** message comes from configured chat_id
- **THEN** Bot processes the command normally

#### Scenario: Unauthorized user
- **WHEN** message comes from a different chat_id
- **THEN** Bot ignores the message and logs a warning
