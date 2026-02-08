## MODIFIED Requirements

### Requirement: Settings management via inline keyboard
The system SHALL provide a `/settings` command that displays all configurable parameters as inline keyboard buttons. Each parameter MUST be editable through the Bot conversation. The keyword settings MUST use an inline keyboard panel showing current keywords as deletable buttons, with action buttons for adding include/exclude keywords, clearing all, and confirming.

#### Scenario: View settings menu
- **WHEN** user sends `/settings`
- **THEN** Bot displays inline keyboard with buttons: 模式(Mode), 地區(Region), 區域(Districts), 價格(Price), 坪數(Size), 關鍵字(Keywords), 排程(Schedule), 通知(Notifications)

#### Scenario: Change search mode
- **WHEN** user taps "模式" button
- **THEN** Bot shows inline keyboard with "買房(Buy)" and "租房(Rent)" options
- **WHEN** user selects one
- **THEN** system updates mode in DB and confirms with "已更新搜尋模式為: 買房"

#### Scenario: Change districts
- **WHEN** user taps "區域" button
- **THEN** Bot shows inline keyboard with all districts for current region, pre-checked districts have ✅ prefix
- **WHEN** user taps a district to toggle, then taps "確認" button
- **THEN** system updates districts in DB and confirms with selected district list

#### Scenario: Change price range
- **WHEN** user taps "價格" button
- **THEN** Bot asks user to input price range in format "min-max" (e.g., "1000-2000")
- **WHEN** user inputs valid range
- **THEN** system updates price_min and price_max in DB and confirms

#### Scenario: Invalid price input
- **WHEN** user inputs invalid price format
- **THEN** Bot responds with error message and example of correct format, allowing retry

#### Scenario: Enter keyword settings
- **WHEN** user taps "關鍵字" button
- **THEN** Bot displays keyword panel with: current include keywords as "包含: {keyword}" buttons, current exclude keywords as "排除: {keyword}" buttons, and action row with "➕ 包含", "➖ 排除", "🗑 清除", "✅ 完成" buttons
- **WHEN** no keywords exist
- **THEN** Bot displays empty state message "尚無關鍵字" with only "➕ 包含", "➖ 排除", "✅ 完成" buttons

#### Scenario: Delete a keyword by tapping
- **WHEN** user taps an existing keyword button (include or exclude)
- **THEN** system removes that keyword from the corresponding list in DB
- **THEN** Bot refreshes the keyword panel with updated state

#### Scenario: Add include keyword
- **WHEN** user taps "➕ 包含" button
- **THEN** Bot sends message "請輸入要包含的關鍵字："
- **WHEN** user inputs a keyword text
- **THEN** system adds the keyword to include list in DB and refreshes the keyword panel

#### Scenario: Add exclude keyword
- **WHEN** user taps "➖ 排除" button
- **THEN** Bot sends message "請輸入要排除的關鍵字："
- **WHEN** user inputs a keyword text
- **THEN** system adds the keyword to exclude list in DB and refreshes the keyword panel

#### Scenario: Add duplicate keyword
- **WHEN** user inputs a keyword that already exists in the target list
- **THEN** Bot responds "此關鍵字已存在" and refreshes the keyword panel without modification

#### Scenario: Clear all keywords
- **WHEN** user taps "🗑 清除" button
- **THEN** system removes all include and exclude keywords from DB and refreshes the keyword panel showing empty state

#### Scenario: Finish keyword settings
- **WHEN** user taps "✅ 完成" button
- **THEN** Bot confirms "關鍵字設定完成" and exits keyword settings conversation state
