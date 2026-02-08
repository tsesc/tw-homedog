## Context

目前 pipeline 完成後，notifier 逐個發送最多 10 筆完整物件訊息到 Telegram。使用者被動接收，無法總覽、篩選、或標記已讀。當物件多時體驗差，且相同物件在下次 pipeline 執行前不會再通知（靠 `notifications_sent` 表），但一旦通知就無法回顧。

現有 DB 結構：`listings` 存所有爬取到的物件，`notifications_sent` 追蹤已通知的物件，`bot_config` 存設定。

## Goals / Non-Goals

**Goals:**
- 使用者可透過 `/list` 命令互動式瀏覽符合條件的物件（分頁 inline keyboard）
- 支援依區域快速篩選
- 點擊物件可展開詳細資訊
- 已讀物件（查看詳情或手動標記）在未更新前不再推送
- Pipeline 通知改為摘要形式，引導使用者用 /list 查看

**Non-Goals:**
- 不做全文搜尋或排序功能
- 不做物件收藏/標星功能
- 不改變 scraper/matcher 的核心邏輯
- 不支援圖片預覽

## Decisions

### 1. 已讀追蹤機制：新增 `listings_read` 表

**選項 A**: 在 `notifications_sent` 表加 `read_at` 欄位
**選項 B**: 新增獨立的 `listings_read` 表 ✅

選擇 B：已讀和已通知是不同概念。已通知是「系統發過摘要」，已讀是「使用者看過詳情」。分開追蹤語意清晰，不影響現有通知邏輯。

```sql
CREATE TABLE IF NOT EXISTS listings_read (
    source TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    raw_hash TEXT,          -- 標記時的 content hash，物件更新後 hash 變化 → 重新推送
    read_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source, listing_id)
);
```

### 2. 「未更新前不再推送」判斷：用 raw_hash 比對

當使用者標記已讀時，同時記錄該物件當時的 `raw_hash`。下次 matcher 篩選時：
- 如果 `listings_read.raw_hash == listings.raw_hash` → 物件未更新，跳過
- 如果 hash 不同或 listings_read 無記錄 → 物件未讀或已更新，納入結果

這比用 timestamp 更精確，只在內容真正變化時才重新通知。

### 3. 分頁機制：callback_data 帶 offset

Telegram inline keyboard callback_data 限制 64 bytes。使用格式：
- `list:p:{offset}` — 翻頁，offset 為數字
- `list:f:{district}` — 區域篩選
- `list:d:{listing_id}` — 展開詳情
- `list:r:{listing_id}` — 標記已讀
- `list:ra` — 全部標記已讀
- `list:back` — 返回列表

每頁顯示 5 筆摘要（一行一個按鈕），底部加上翻頁和篩選按鈕。

### 4. 通知行為改為摘要

Pipeline 完成後，不再逐個推送物件訊息。改為：
- 如果有新的未讀物件：發送 `"有 N 筆新物件符合條件，使用 /list 查看"`
- 如果沒有新物件：不發送（靜默）

這避免訊息轟炸，讓使用者主動決定何時查看。

### 5. /list 查詢範圍

`/list` 顯示的是 matcher 篩選後的「未讀」物件。流程：
1. `storage.get_unread_matched_listings()` — 取出未讀（或已更新）且未通知的物件
2. 套用 matcher 篩選條件
3. 以分頁 inline keyboard 呈現

## Risks / Trade-offs

- **[分頁資料一致性]** 使用者瀏覽分頁期間可能有新物件加入 → 接受：下次翻頁會自動包含，不影響體驗
- **[Telegram callback_data 64 bytes 限制]** listing_id 通常是 8 位數字，district 是中文 → 對 district 使用 section code (數字) 而非中文名
- **[BREAKING: 通知行為改變]** 舊的逐個推送被移除 → 遷移簡單，只改 notifier 和 pipeline 呼叫處
- **[已讀狀態 DB 膨脹]** 大量物件標記已讀 → `listings_read` 表只存 source+listing_id+hash，資料量小。可定期清理超過 30 天的記錄
