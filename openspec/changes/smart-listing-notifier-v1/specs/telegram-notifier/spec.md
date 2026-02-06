## ADDED Requirements

### Requirement: Notifier SHALL send formatted Telegram messages

系統 SHALL 透過 Telegram Bot API 發送格式化的房源通知訊息。

#### Scenario: Send single listing notification
- **WHEN** 有一筆符合條件的新物件
- **THEN** 系統 SHALL 發送包含以下資訊的 Telegram 訊息：行政區、價格（NT$格式）、坪數、上架時間、物件連結

#### Scenario: Message format
- **WHEN** 發送通知訊息
- **THEN** 訊息格式 SHALL 使用結構化排版（含 emoji 標示），包含可點擊的物件連結

### Requirement: Notifier SHALL prevent duplicate notifications

同一物件 MUST 只通知一次。

#### Scenario: First notification for listing
- **WHEN** 物件首次符合條件且未通知過
- **THEN** 系統 SHALL 發送通知並記錄到 notifications_sent

#### Scenario: Repeated match of same listing
- **WHEN** 已通知過的物件再次出現在匹配結果中
- **THEN** 系統 SHALL 跳過該物件，不重複發送

### Requirement: Notifier SHALL handle send failures

通知發送失敗 MUST 被妥善處理。

#### Scenario: Telegram API error
- **WHEN** Telegram API 回傳錯誤（如 rate limit, network error）
- **THEN** 系統 SHALL 記錄 error log，該物件不標記為已通知，下次執行時重試

#### Scenario: Invalid bot token
- **WHEN** 設定的 Telegram Bot Token 無效
- **THEN** 系統 SHALL 在啟動時驗證並拋出明確的錯誤訊息

### Requirement: Notifier SHALL respect rate limits

系統 SHALL 避免觸發 Telegram API rate limit。

#### Scenario: Batch notifications
- **WHEN** 單次執行有多筆符合條件的物件
- **THEN** 系統 SHALL 每則通知之間間隔至少 1 秒，單次最多發送 10 則
