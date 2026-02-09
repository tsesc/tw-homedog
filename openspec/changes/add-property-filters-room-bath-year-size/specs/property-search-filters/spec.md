## ADDED Requirements

### Requirement: Persisted filter fields
The system SHALL support persisted search filters for room counts, bathroom counts, building year range, and size range. Config YAML and DB config MUST accept:
- `search.room_counts`: array of integers (allowed values: 1-5) meaning acceptable bedroom counts.
- `search.bathroom_counts`: array of integers (allowed values: 1-5) meaning acceptable bathroom counts.
- `search.year_built.min` / `search.year_built.max`: four-digit years; `min` <= `max`.
- `search.size.min_ping` / `search.size.max_ping`: numeric (float/int) pings; `min` <= `max` when both present.
Empty arrays or null values MUST disable the corresponding filter without validation errors. Defaults MUST remain backward compatible (all new fields unset).

#### Scenario: Load config with new filters
- **WHEN** DB config stores `search.room_counts` = [1,3], `search.bathroom_counts` = [2], `search.year_built` = {"min": 2000, "max": 2015}, `search.size` = {"min_ping": 18, "max_ping": 40}
- **THEN** `Config.search` exposes `room_counts=[1,3]`, `bathroom_counts=[2]`, `year_built_min=2000`, `year_built_max=2015`, `min_ping=18`, `max_ping=40`

#### Scenario: Reject inverted ranges
- **WHEN** user attempts to set `year_built.min` to 2025 and `year_built.max` to 2000 (or `size.max_ping` < `size.min_ping`)
- **THEN** validation fails with a clear error and the previous saved values remain unchanged

### Requirement: Telegram settings for filters
The Bot `/settings` flow SHALL let users view and edit the new filters. It MUST provide inline keyboard options for room counts (1房/2房/3房) and bathroom counts (1衛/2衛), and text prompts for year and size ranges using `min-max` format (e.g., `2000-2015`, `20-40`). `/status` MUST display the active selections, or "未設定" when unset.

#### Scenario: Set room/bath filters
- **WHEN** user opens `/settings` → "格局" and selects 2房 and 3房, then selects 2衛
- **THEN** system saves `room_counts=[2,3]`, `bathroom_counts=[2]` in DB and confirms "已更新：2-3 房，2 衛"

#### Scenario: Set year and size ranges
- **WHEN** user enters `2005-2012` for building year and `20-45` for 坪數
- **THEN** Bot validates the ranges, saves them, and `/status` shows "屋齡：2005-2012 年" and "坪數：20-45 坪"

#### Scenario: Invalid range input
- **WHEN** user inputs `2015-2000` for year range
- **THEN** Bot responds with an error explaining `最小年份需小於最大年份`, keeps previous values, and re-prompts

### Requirement: Search requests carry filters
The scraper SHALL include the new filters in provider requests whenever supported. For 591 buy/rent endpoints:
- Room filter MUST constrain results to the selected `room_counts` values.
- Bathroom filter MUST constrain results to the selected `bathroom_counts` values.
- Size filter MUST send both min and max when provided (e.g., `area=20_45`), or min-only when only min is set.
- Building year filter MUST be translated to provider-supported parameters when possible; otherwise it is handled post-fetch (see matcher requirement).
When no filters are set, request parameters MUST match current behavior.

#### Scenario: Build buy search params with filters
- **WHEN** `room_counts=[2,3]`, `bathroom_counts=[2]`, `size.min_ping=18`, `size.max_ping=35`
- **THEN** buy search params include room and bathroom constraints plus `area=18_35`; no other default params are altered

### Requirement: Match engine enforces filters on listings
After scraping, the matcher SHALL enforce all active filters before sending notifications:
- Listing passes room/bath filters only if parsed bedroom and bathroom counts are within the configured sets. Counts MUST be parsed from fields like `room` text (e.g., `3房2廳2衛`) and detail data; unknown counts MUST NOT cause rejection.
- Size filter MUST reject listings with `size_ping` below `min_ping` or above `max_ping` when set.
- Building year filter MUST compute build year from available data (prefer explicit build year; otherwise derive from `houseage` by `current_year - age`) and reject listings outside the configured year range. Missing data MUST not reject the listing.

#### Scenario: Matching with all filters
- **WHEN** filters are `room_counts=[3]`, `bathroom_counts=[2]`, `size 20-40 坪`, `year 2000-2015`
- **THEN** a listing with `room="3房2廳2衛"`, `size_ping=28`, `houseage="15年"` (build year 2011) MATCHES
- **AND** a listing with `room="2房1廳1衛"` or `size_ping=18` or build year 1995 is REJECTED

#### Scenario: Missing structured data
- **WHEN** a listing lacks bathroom count and build year
- **THEN** matcher ignores those filters for that listing, but still applies available size and keyword/price/district filters

### Requirement: Store and display key location details
The system SHALL persist address, floor, and community name for each listing when available, without rejecting inserts if a field is missing. `/list` detail messages and notification payloads MUST surface these fields when present so users can quickly judge relevance.

#### Scenario: Save and show location fields
- **WHEN** a listing contains `address="台北市大安區復興南路"`, `floor="5F/12F"`, `community_name="XX社區"`
- **THEN** the DB row stores these values, and `/list` detail view includes address, floor, and community lines in the message
