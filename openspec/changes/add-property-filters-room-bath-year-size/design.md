## Context
- Current filters cover mode, region/districts, price range, min坪數, keywords, and paging. Rooms、衛浴、建物年份、坪數上限 are absent.
- Config flows: Telegram `/settings` → SQLite `bot_config` (JSON strings) → `DbConfig.build_config()` → `Config` dataclass → scraper (rent Playwright, buy BFF API) → matcher → notifier.
- Scraper already supports min坪數 via query param (`area=min_`) but not max坪數/房/衛/屋齡. Matcher only checks price/district/min坪/keywords.
- Listings table already has address/floor/community columns, but some sources may not populate; `/list` notifications currently omit address/floor.

## Goals / Non-Goals
**Goals:**
- Add filters for room count (1/2/3 房) and bathroom count (1/2 衛) usable in both rent & buy flows.
- Add building year range filter and full size range (min+max 坪) with validation and defaults.
- Expose filters in Telegram `/settings` + `/status` and CLI/YAML; persist in DB; keep backward compatibility.
- Apply filters in scraper request params when supported; always enforce in matcher before notifications.
- Ensure stored listings reliably capture社區/樓層/地址 (when available) and surface them in `/list` detail messages for better context.

**Non-Goals:**
- Changing providers beyond 591 or altering crawl strategy.
- Full UI redesign of `/settings` beyond the new filter controls.
- Handling half-bath granularity or complex layouts (e.g., 4房以上) unless derived from simple counts.

## Decisions
- **Data model & storage**: Extend `SearchConfig` with `room_counts: list[int]`, `bathroom_counts: list[int]`, `year_built_min/max: int|None`, `max_ping: float|None`. Add defaults to `DEFAULTS` and DB config keys (JSON arrays/nullable). Validation: counts within 1–5; min<=max for year & size when both present.
- **Config sources**: YAML keys `search.room_counts`, `search.bathroom_counts`, `search.year_built.min/max`, `search.size.min_ping/max_ping`. DbConfig supports the same dotted keys; missing keys default to None/[].
- **Bot UX**: `/settings` adds a "格局" panel with inline multi-select chips for 1房/2房/3房 and 1衛/2衛 plus "清除". Year/坪數 ranges collected via text `min-max`; validation errors keep prior values and re-prompt. `/status` prints human-friendly summary or "未設定".
- **Scraper (buy)**: When counts/ranges set, include provider params (room/bath, `area=min_max`). Building year converts to `houseage` range using `age_min = current_year - year_built_max`, `age_max = current_year - year_built_min`; if provider lacks a year filter, skip here and rely on matcher.
- **Scraper (rent)**: Enhance `build_search_url` to add `area=min_max` and room/bath params matching 591 query fields; continue Playwright flow unchanged otherwise.
- **Matcher**: Add parsers for room/bath counts from strings like `3房2廳2衛` (regex). Apply inclusive checks against configured sets. Size check supports both min and max. Building year computed from explicit year if available, else from `houseage` numeric part; listings lacking data are not auto-rejected.
- **Display & serialization**: Update `/status` formatting, task summaries, and any saved templates/examples to include the new filters without breaking older configs.
- **Notification content**: Extend `format_listing_message` (used by `/list` + pushes) to include address, floor, and community when present.
- **Testing**: Add unit tests for config validation (ranges, defaults), scraper param construction (buy/rent), matcher logic for room/bath/year/size, and bot flows for valid/invalid inputs.

## Risks / Trade-offs
- 591 param names/behaviors for room/bath/year may differ between rent and buy; may require inspection and could break if undocumented.
- Many listings omit build year/house age; relying on matcher may let undesired listings through (acceptable to avoid false negatives).
- Parsing room/bath from free-text may miscount edge cases (e.g., "開放式"), risking false positives/negatives.
- Additional query params might reduce result volume or trigger anti-scraping defenses; need logging and fallback.

## Migration Plan
- Add new fields and defaults to config/dataclass and DbConfig; ensure migrations set missing keys to None/[] rather than erroring.
- Update CLI config examples and Telegram templates/prompts.
- Implement scraper & matcher changes with feature-flag-free rollout (disabled by default when unset).
- Extend tests; run `uv run pytest`.

## Open Questions
- Should we support "3房以上" or only explicit counts? (Plan: explicit 1/2/3 now.)
- Are half-baths represented in data, and how should they round? (Plan: floor to nearest int for now.)
- Does 591 expose build-year or only house age? If none, do we consider post-fetch filtering sufficient?
