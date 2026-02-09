## Why

Current property search lacks precise filters for layout, building age, and area, making users sift through irrelevant listings. Adding room/bath counts plus year and size ranges will improve relevance and conversion.

## What Changes

- Add selectable room-count filter (e.g., 1房, 2房, 3房+) and bathroom-count filter (1衛, 2衛+).
- Add building year range filter (min/max year) to target newer or classic properties.
- Add size (坪數) range filter with sensible defaults and validation.
- Wire filters through UI state, query params, and backend search so results reflect selections.
- Update listing fetch API/docs to include new filter parameters and ensure empty filters keep current behavior.
- Persist community name、樓層、地址欄位到 DB，並在 /list 推送時一併呈現關鍵資訊。

## Capabilities

### New Capabilities
- `property-search-filters`: Search supports room/bath count and building year/area range filters in UI and API, preserving backward compatibility when unset.

### Modified Capabilities
- `<existing-name>`: <what requirement is changing>

## Impact

- Frontend search/filter components and URL/query-state handling.
- API layer and search/query builder to accept and apply new filter parameters.
- Storage schema/serializers and notifier payloads to store/emit 社區、樓層、地址資訊。
- Analytics/tracking for filter usage (if present) and QA test cases for combined filters.
