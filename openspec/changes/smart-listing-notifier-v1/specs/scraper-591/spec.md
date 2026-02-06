## ADDED Requirements

### Requirement: Scraper SHALL collect listing IDs from 591 search results

系統 SHALL 使用 Playwright headless 模式瀏覽 591 租屋搜尋結果頁，根據設定檔中的搜尋條件（region, districts, price range, area）組合 URL 參數，收集所有符合條件的 listing ID。

#### Scenario: Successful listing ID collection
- **WHEN** scraper 以有效的搜尋條件執行
- **THEN** 系統從搜尋結果頁提取所有 listing ID（7-8 位數字），並回傳 listing ID 列表

#### Scenario: Multiple pages of results
- **WHEN** 搜尋結果超過一頁
- **THEN** 系統 SHALL 透過翻頁或捲動，最多收集前 N 頁的結果（N 由設定檔定義，預設 3）

#### Scenario: No results found
- **WHEN** 搜尋條件沒有匹配的物件
- **THEN** 系統 SHALL 回傳空列表，並記錄 info level log

### Requirement: Scraper SHALL extract listing details via HTTP

系統 SHALL 對每個 listing ID 使用 HTTP GET 請求取得物件詳情頁面，並解析出結構化資料。

#### Scenario: Successful detail extraction
- **WHEN** 以有效 listing ID 請求詳情
- **THEN** 系統 SHALL 解析出 title, price, address, district, size_ping, floor, layout, published_at, url 等欄位

#### Scenario: Listing removed (404)
- **WHEN** listing ID 對應的頁面回傳 404
- **THEN** 系統 SHALL 跳過該物件，記錄 warning log，繼續處理下一個

#### Scenario: Request timeout
- **WHEN** HTTP 請求超過 timeout（預設 30 秒）
- **THEN** 系統 SHALL 重試最多 3 次，每次間隔指數遞增（2s, 4s, 8s）

### Requirement: Scraper SHALL implement anti-detection measures

系統 MUST 實作反爬策略以降低被封鎖風險。

#### Scenario: Request spacing
- **WHEN** 連續請求多個物件詳情
- **THEN** 每次請求之間 SHALL 等待隨機 2-5 秒

#### Scenario: User-Agent rotation
- **WHEN** 發送 HTTP 請求
- **THEN** SHALL 從預設的 User-Agent 列表中隨機選擇一個

### Requirement: Scraper SHALL support configurable search parameters

爬蟲的搜尋條件 MUST 完全由設定檔驅動，不得 hardcode。

#### Scenario: Search with district filter
- **WHEN** 設定檔指定 districts: ["Daan", "Zhongshan"]
- **THEN** 系統 SHALL 只搜尋大安區與中山區的物件

#### Scenario: Search with price range
- **WHEN** 設定檔指定 price.min: 20000, price.max: 40000
- **THEN** 系統 SHALL 在搜尋 URL 中帶入對應的價格參數
