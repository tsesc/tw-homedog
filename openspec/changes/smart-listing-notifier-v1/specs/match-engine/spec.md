## ADDED Requirements

### Requirement: Matcher SHALL filter listings by price range

系統 SHALL 根據設定檔中的價格範圍篩選物件。

#### Scenario: Listing within price range
- **WHEN** 物件價格 35000，設定 price.min: 20000, price.max: 40000
- **THEN** 該物件 SHALL 通過價格篩選

#### Scenario: Listing outside price range
- **WHEN** 物件價格 50000，設定 price.max: 40000
- **THEN** 該物件 SHALL 被排除

#### Scenario: Open-ended price range
- **WHEN** 只設定 price.min 未設定 price.max
- **THEN** 系統 SHALL 只篩選下限，不設上限

### Requirement: Matcher SHALL filter listings by district

系統 SHALL 根據設定檔中的行政區列表篩選物件。

#### Scenario: Listing in target district
- **WHEN** 物件位於大安區，設定 districts: ["Daan", "Zhongshan"]
- **THEN** 該物件 SHALL 通過行政區篩選

#### Scenario: Listing not in target district
- **WHEN** 物件位於萬華區，設定 districts: ["Daan", "Zhongshan"]
- **THEN** 該物件 SHALL 被排除

### Requirement: Matcher SHALL filter listings by size

系統 SHALL 根據設定檔中的最小坪數篩選物件。

#### Scenario: Listing meets minimum size
- **WHEN** 物件坪數 28，設定 size.min_ping: 20
- **THEN** 該物件 SHALL 通過坪數篩選

#### Scenario: Listing below minimum size
- **WHEN** 物件坪數 15，設定 size.min_ping: 20
- **THEN** 該物件 SHALL 被排除

### Requirement: Matcher SHALL filter listings by keywords

系統 SHALL 支援 include 和 exclude 關鍵字篩選。

#### Scenario: Include keyword match
- **WHEN** 物件標題包含 "電梯"，設定 keywords.include: ["電梯"]
- **THEN** 該物件 SHALL 通過關鍵字篩選（需包含所有 include 關鍵字）

#### Scenario: Exclude keyword match
- **WHEN** 物件標題包含 "頂樓"，設定 keywords.exclude: ["頂樓"]
- **THEN** 該物件 SHALL 被排除

#### Scenario: No keywords configured
- **WHEN** 設定檔未定義 keywords
- **THEN** 系統 SHALL 跳過關鍵字篩選，所有物件通過

### Requirement: Matcher SHALL only match new listings

系統 SHALL 只匹配尚未通知過的新物件。

#### Scenario: New unnotified listing matches
- **WHEN** 物件符合所有條件且未被通知過
- **THEN** 該物件 SHALL 出現在匹配結果中

#### Scenario: Already notified listing
- **WHEN** 物件符合所有條件但已被通知過
- **THEN** 該物件 SHALL 不出現在匹配結果中
