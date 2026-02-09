## Why

591 同一間房常由多位房仲重複刊登，造成通知、列表與資料庫累積大量重複資料，影響判讀效率。需要在爬蟲寫入前就去重，並且對既有資料做一次性清理，恢復資料品質。

## What Changes

- 新增房源去重演算法，對新抓到的物件與資料庫既有物件比對，命中重複時跳過寫入。
- 引入可解釋的重複判定規則（地址正規化、坪數/價格容忍度、關鍵文本特徵、相似度分數）。
- 新增批次清理流程，掃描現有資料庫重複群組並合併/移除重複資料。
- 清理時保留關聯資料：已讀狀態、通知狀態、最愛標記與可追溯的主記錄。
- 新增去重結果統計（略過數、合併數、保留數）與可回溯日誌。

## Capabilities

### New Capabilities

- `listing-deduplication`: 在爬蟲與資料清理流程中，透過規則化比對與分數判定識別同一物件，避免重複入庫並清除歷史重複資料。

### Modified Capabilities

## Impact

- `scraper.py`、`normalizer.py`、`storage.py` 與 pipeline 流程（scrape/insert/cleanup）。
- SQLite schema 與 migration（去重索引、清理批次輔助欄位或映射表）。
- `/list`、通知、已讀、最愛等依賴 listing_id 的資料一致性處理。
- 新增管理指令或維護任務以執行既有資料清理。
