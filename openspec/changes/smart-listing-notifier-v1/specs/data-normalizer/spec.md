## ADDED Requirements

### Requirement: Normalizer SHALL convert raw 591 data to unified listing format

系統 SHALL 將 591 爬蟲取得的原始 HTML 解析結果轉換為統一的 listing 結構。

#### Scenario: Full data normalization
- **WHEN** 收到一筆完整的 591 原始物件資料
- **THEN** 系統 SHALL 輸出包含以下欄位的統一結構：source, listing_id, title, price (int), address, district, size_ping (float), floor, url, published_at, raw_hash (SHA256)

#### Scenario: Missing optional fields
- **WHEN** 原始資料缺少某些非必要欄位（如 floor, size_ping）
- **THEN** 系統 SHALL 將缺失欄位設為 None/null，不影響其他欄位的正規化

#### Scenario: Price extraction from various formats
- **WHEN** 價格以不同格式呈現（如 "35,000 元/月", "NT$35000"）
- **THEN** 系統 SHALL 正確提取數字部分並轉為整數

### Requirement: Normalizer SHALL generate content hash

系統 SHALL 為每筆物件生成基於內容的 SHA256 hash，用於去重。

#### Scenario: Hash generation
- **WHEN** 正規化一筆物件資料
- **THEN** 系統 SHALL 基於 title + price + address 組合生成 SHA256 hash

#### Scenario: Same content different listing_id
- **WHEN** 兩筆物件有不同 listing_id 但相同 title, price, address
- **THEN** 兩者 SHALL 產生相同的 raw_hash
