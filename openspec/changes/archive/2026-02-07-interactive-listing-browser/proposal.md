## Why

目前系統在 pipeline 執行後逐個推送符合條件的物件訊息，使用者無法總覽、篩選或選擇性查看。當符合條件的物件較多時，訊息轟炸體驗差，且無法標記「已讀」來避免重複通知。需要一套互動式物件瀏覽機制，讓使用者主動瀏覽、篩選、選擇查看，並能標記已讀。

## What Changes

- 新增 `/list` 命令，以分頁 inline keyboard 顯示符合條件的物件摘要列表
- 支援 inline keyboard 篩選：依區域、價格區間快速 filter
- 點擊物件按鈕展開詳細資訊（取代自動推送）
- 新增「已讀」機制：查看詳情或手動標記後，該物件在未更新前不再推送
- Pipeline 通知行為改為摘要通知（「有 N 筆新物件符合條件，使用 /list 查看」），不再逐個推送
- **BREAKING**: `send_notifications()` 不再逐個推送完整物件訊息，改為摘要通知

## Capabilities

### New Capabilities
- `listing-browser`: 互動式物件瀏覽功能，包含 /list 命令、分頁、篩選、詳情展開
- `listing-read-status`: 物件已讀狀態追蹤，包含 DB schema、已讀標記、通知過濾邏輯

### Modified Capabilities
- `telegram-bot-handler`: 新增 /list 命令，修改 pipeline 通知行為從逐個推送改為摘要通知

## Impact

- **storage.py**: 新增 `listings_read` 表或在 `notifications_sent` 加欄位追蹤已讀狀態；新增查詢方法支援分頁、篩選
- **bot.py**: 新增 /list 命令 handler、分頁 callback、篩選 callback、詳情展開 callback
- **notifier.py**: `send_notifications()` 改為發送摘要訊息
- **matcher.py**: `find_matching_listings()` 需支援排除已讀物件
