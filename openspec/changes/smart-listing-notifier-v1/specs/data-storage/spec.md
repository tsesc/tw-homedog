## ADDED Requirements

### Requirement: System SHALL store listings in SQLite database

系統 SHALL 使用 SQLite 資料庫存儲所有爬取的物件資料，資料庫檔案路徑由設定檔指定。

#### Scenario: First run creates database
- **WHEN** 系統首次執行且資料庫檔案不存在
- **THEN** 系統 SHALL 自動建立資料庫檔案並初始化所有表結構

#### Scenario: Store new listing
- **WHEN** 爬蟲取得一筆新物件資料
- **THEN** 系統 SHALL 將正規化後的物件寫入 `listings` 表，包含 source, listing_id, title, price, address, district, size_ping, floor, url, published_at, raw_hash, created_at

### Requirement: System SHALL deduplicate listings

系統 MUST 避免重複寫入相同物件。

#### Scenario: Duplicate by source + listing_id
- **WHEN** 嘗試寫入一筆已存在相同 source 和 listing_id 的物件
- **THEN** 系統 SHALL 跳過寫入，不產生錯誤

#### Scenario: Duplicate detection by content hash
- **WHEN** listing_id 不同但 raw_hash（內容 SHA256）相同
- **THEN** 系統 SHALL 視為重複物件，跳過寫入

### Requirement: System SHALL track notification history

系統 SHALL 記錄每筆物件的通知狀態，避免重複通知。

#### Scenario: Record sent notification
- **WHEN** 成功發送一則 Telegram 通知
- **THEN** 系統 SHALL 在 `notifications_sent` 表寫入 listing_id, source, notified_at, channel

#### Scenario: Check if already notified
- **WHEN** 條件比對引擎找到符合條件的物件
- **THEN** 系統 SHALL 先查詢 `notifications_sent` 表，已通知過的物件不再重複通知
