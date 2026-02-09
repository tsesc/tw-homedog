## 1. Config & Validation

- [x] 1.1 Extend `SearchConfig`/defaults/DbConfig to store `room_counts`, `bathroom_counts`, `year_built_min/max`, `max_ping`; keep backward-compatible defaults.
- [x] 1.2 Add validation for count ranges (1–5) and min/max ordering for year/size; surface clear errors on bad input.
- [x] 1.3 Update YAML parsing, config examples/templates, and persisted DB keys for the new filters.

## 2. Bot UX & Status

- [x] 2.1 Add `/settings` UI: inline multi-select for 房/衛 counts plus text prompts for 年份/坪數 ranges with validation + clear actions.
- [x] 2.2 Update `/status` summary to display active 房/衛/年份/坪數 filters or "未設定" when absent.
- [x] 2.3 Include address/樓層/社區 in `/list` detail messages when data exists.

## 3. Scraper & Matcher

- [x] 3.1 Update rent and buy search parameter builders to include room/bath filters and full size range; translate year range to provider params when available.
- [x] 3.2 Enhance matcher to parse room/bath counts from listing text, enforce size max and year range (using houseage→build year), without rejecting listings lacking data.
- [x] 3.3 Ensure scraper/normalizer persist address、樓層、社區欄位 and they flow through storage/notifier without breaking existing data.

## 4. Tests & Docs

- [x] 4.1 Add/adjust unit tests for config loader, DbConfig round-trip, scraper param construction, and matcher filter logic.
- [x] 4.2 Add/adjust bot flow tests (or integration) for setting/validating new filters and update README/usage notes if needed.
