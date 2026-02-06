## ADDED Requirements

### Requirement: System SHALL load configuration from YAML file

系統 SHALL 從 YAML 設定檔載入所有運行參數。

#### Scenario: Load valid config
- **WHEN** 系統啟動且 config.yaml 存在且格式正確
- **THEN** 系統 SHALL 成功載入搜尋條件、Telegram 設定、資料庫路徑等所有參數

#### Scenario: Config file not found
- **WHEN** 指定的設定檔路徑不存在
- **THEN** 系統 SHALL 拋出明確的 FileNotFoundError 訊息，提示使用者複製 config.example.yaml

#### Scenario: Invalid YAML format
- **WHEN** 設定檔 YAML 格式錯誤
- **THEN** 系統 SHALL 拋出解析錯誤，包含行號與錯誤描述

### Requirement: System SHALL validate configuration schema

系統 MUST 在啟動時驗證設定檔的必要欄位與值類型。

#### Scenario: Missing required field
- **WHEN** 設定檔缺少必要欄位（如 telegram.bot_token）
- **THEN** 系統 SHALL 拋出 ValidationError，列出所有缺失的必要欄位

#### Scenario: Invalid value type
- **WHEN** 設定檔中 price.min 的值為字串而非數字
- **THEN** 系統 SHALL 拋出型別錯誤，指明欄位名稱與預期類型

### Requirement: System SHALL provide example configuration

專案 MUST 包含 `config.example.yaml` 範例檔案。

#### Scenario: Example config completeness
- **WHEN** 使用者複製 config.example.yaml
- **THEN** 範例檔 SHALL 包含所有可設定項目與說明註解，使用者只需修改值即可使用

### Requirement: System SHALL support CLI config path override

系統 SHALL 允許透過 CLI 參數指定設定檔路徑。

#### Scenario: Custom config path
- **WHEN** 執行 `python -m tw_homedog run --config /path/to/my-config.yaml`
- **THEN** 系統 SHALL 使用指定路徑的設定檔

#### Scenario: Default config path
- **WHEN** 未指定 --config 參數
- **THEN** 系統 SHALL 使用當前目錄下的 `config.yaml`
