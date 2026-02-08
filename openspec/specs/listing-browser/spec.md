## ADDED Requirements

### Requirement: List command with paginated display
The system SHALL provide a `/list` command that displays matched unread listings as a paginated inline keyboard. Each page SHALL show up to 5 listings as buttons with summary text (district, price, size). Navigation buttons SHALL allow paging forward and backward.

#### Scenario: View listing list
- **WHEN** user sends `/list` and there are matched unread listings
- **THEN** Bot displays first page of up to 5 listings as inline keyboard buttons, each showing "{district} {price} {size}" summary, with navigation row showing page info and next/prev buttons

#### Scenario: Empty listing list
- **WHEN** user sends `/list` and there are no matched unread listings
- **THEN** Bot responds with "目前沒有未讀的符合條件物件"

#### Scenario: Page forward
- **WHEN** user taps "下一頁 ▶" button
- **THEN** Bot updates message to show next page of listings with updated page indicator

#### Scenario: Page backward
- **WHEN** user taps "◀ 上一頁" button
- **THEN** Bot updates message to show previous page of listings with updated page indicator

#### Scenario: Single page
- **WHEN** total matched unread listings fit in one page (≤ 5)
- **THEN** Bot does not show next/prev navigation buttons

### Requirement: District filter
The system SHALL provide inline keyboard filter buttons to narrow listings by district. Tapping a district filter SHALL show only listings in that district.

#### Scenario: View filter options
- **WHEN** user taps "篩選" button on the listing list
- **THEN** Bot displays inline keyboard with available districts from current results, plus "全部" to clear filter

#### Scenario: Apply district filter
- **WHEN** user taps a district filter button
- **THEN** Bot updates listing list to show only listings in that district, resets to page 1

#### Scenario: Clear filter
- **WHEN** user taps "全部" filter button
- **THEN** Bot shows all matched unread listings without district filter, resets to page 1

### Requirement: Listing detail view
The system SHALL show full listing details when user taps a listing button. The detail view SHALL include all available fields and action buttons.

#### Scenario: View listing detail
- **WHEN** user taps a listing summary button
- **THEN** Bot updates message to show full listing details (same format as current notification message) with action buttons: "✅ 已讀", "◀ 返回列表", and "🔗 開啟連結" (URL button)

#### Scenario: View detail auto-marks as read
- **WHEN** user views a listing detail
- **THEN** system records the listing as read with current raw_hash

#### Scenario: Return to list from detail
- **WHEN** user taps "◀ 返回列表" button from detail view
- **THEN** Bot returns to the listing list at the same page, with the viewed listing now excluded (marked read)

### Requirement: Mark all as read
The system SHALL provide a button to mark all currently displayed listings as read at once.

#### Scenario: Mark all as read
- **WHEN** user taps "全部已讀" button on the listing list
- **THEN** system marks all currently matched unread listings as read
- **THEN** Bot responds with "已將 N 筆物件標記為已讀"

#### Scenario: Mark all as read with filter active
- **WHEN** user taps "全部已讀" button while a district filter is active
- **THEN** system marks only the filtered listings as read (not all matched listings)
- **THEN** Bot responds with "已將 N 筆物件標記為已讀"
