## ADDED Requirements

### Requirement: System SHALL support cron-based scheduling

系統 SHALL 提供可由 cron 觸發的 CLI 入口，執行完整的 scrape → match → notify 流程。

#### Scenario: Full pipeline execution via CLI
- **WHEN** 執行 `python -m tw_homedog run`
- **THEN** 系統 SHALL 依序執行：爬取物件 → 正規化 → 寫入 DB → 條件比對 → 發送通知

#### Scenario: Cron integration
- **WHEN** 使用者設定 cron job `*/15 * * * *` 觸發
- **THEN** 系統 SHALL 每 15 分鐘自動執行完整流程

### Requirement: System SHALL support individual subcommands

系統 SHALL 提供子命令以支援手動調試。

#### Scenario: Scrape only
- **WHEN** 執行 `python -m tw_homedog scrape`
- **THEN** 系統 SHALL 只執行爬蟲，將結果寫入 DB，不觸發通知

#### Scenario: Notify only
- **WHEN** 執行 `python -m tw_homedog notify`
- **THEN** 系統 SHALL 對 DB 中尚未通知的符合條件物件發送通知

### Requirement: System SHALL handle execution failures gracefully

單次排程失敗 MUST NOT 影響後續執行。

#### Scenario: Scraper failure
- **WHEN** 爬蟲模組執行失敗（如 591 無法連線）
- **THEN** 系統 SHALL 記錄 error log 並正常退出（exit code 1），不影響下次 cron 觸發

#### Scenario: Partial failure
- **WHEN** 部分物件提取失敗但其他物件成功
- **THEN** 系統 SHALL 繼續處理成功的物件，失敗的記錄 warning log
