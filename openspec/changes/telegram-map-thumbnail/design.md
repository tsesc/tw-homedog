## Context
- Telegram listing pushes currently include photos and pricing but not address context or a visual map, so reviewers must copy/paste into maps manually.
- Listings already store address fields; lat/lng may or may not be present (assume at least a human-readable address). Telegram messages can include both text and an image thumbnail via `sendPhoto` or `sendMediaGroup`.
- Google Maps Static Maps API can return a small PNG when given center coordinates or address; it requires an API key and respects URL size limits.

## Goals / Non-Goals

**Goals:**
- Append the formatted property address to Telegram listing pushes.
- Generate and attach a map thumbnail centered on the listing location with a marker for quick spatial context.
- Provide graceful degradation (text-only) when address/coords are missing or the Maps API fails/quotas out.
- Limit API usage with caching/reuse so pushes stay within budget and remain fast.

**Non-Goals:**
- Interactive maps or deep-links to custom map UI (keep using Google Maps URL for click-through if needed).
- Building a geocoding pipeline or bulk address cleanup; only lightweight on-demand geocode if coords absent.
- Changing upstream listing ingestion or editing address data quality.

## Decisions
- **Static Maps provider**: Use Google Maps Static Maps API for reliability, styling flexibility, and marker support; fall back to no-image if the request fails. Alternatives (OpenStreetMap tile stitching) skipped to avoid hosting tiles and legal complexity.
- **Address vs coordinates**: Prefer stored lat/lng when available; otherwise request a single geocode lookup for the address (cache the result) to reduce repeated API calls and improve thumbnail accuracy.
- **Image generation**: Build the request URL with deterministic parameters (size ~640x400, zoom tuned for urban vs suburban default, red marker). Cache by listing id + address hash; store either in temp storage or reuse Telegram `file_id` after first upload to avoid repeated bytes.
- **Message formatting**: Keep existing photo carousel; include map thumbnail as the first media item when present, with caption containing address + price + key facts. If using `sendPhoto` single message flow, prepend map then follow with gallery; otherwise fallback to appending address text only.
- **Configuration**: Add env vars for `GOOGLE_MAPS_API_KEY`, optional `MAP_STYLE`, `MAP_STATIC_BASE_URL` (default Google), `MAP_IMAGE_CACHE_TTL`, and a feature flag to disable map attachments quickly.
- **Error handling**: If geocode or map fetch fails or quota exceeded, log, increment metric, and continue sending text-only message; never block the push.

## Risks / Trade-offs
- **Quota/cost spikes** → Mitigate with caching, reuse Telegram `file_id`, rate limiting per minute, and feature-flag rollback.
- **Poor address quality** → Mitigate with normalization (strip unit, city, country defaults) and fallback to text-only when geocode confidence is low.
- **Latency from map fetch** → Mitigate via background prefetch before push, or concurrent fetch with message construction plus short timeout and skip on timeout.
- **Privacy/precision** → Use rounded coordinates or zoom 16 default; avoid showing exact entrance if privacy concerns, and gate by feature flag per channel.

## Migration Plan
- Add configuration defaults and secret plumbing; deploy behind feature flag off by default.
- Implement map URL builder + caching and wire into Telegram push pipeline; log metrics.
- Enable flag in staging; verify sample listings with/without coords; confirm message formatting.
- Roll out flag per channel; monitor quota and error logs; keep ability to disable quickly.

## Open Questions
- Do we already persist lat/lng for all listings? If not, which geocoding service and quota should we use (Google Geocoding vs Places)?
- Preferred map zoom/style (satellite vs roadmap) and language/region parameters for Taiwan audiences?
- Should we store generated images or only reuse Telegram `file_id`? If storage, where (S3/CDN vs local temp)?
