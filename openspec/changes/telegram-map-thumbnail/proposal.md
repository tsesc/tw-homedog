## Why
Current Telegram listing pushes show only photos and price, so reviewers can't quickly judge where the property is. Jumping to a map slows triage and misses context (e.g., school zone, transit). Adding the address and a small map preview will speed eyeballing and reduce click-throughs.

## What Changes
- Pull the property's full address when preparing Telegram push content.
- Generate a Google Maps static thumbnail (or fallback image) centered on the address and attach it with the listing push.
- Render the address text alongside the thumbnail for quick scan.
- Handle fallbacks: missing/invalid address, API failures, or rate limits with graceful degradation.
- Add config for Maps API key, size/style options, and caching to control quota usage.

## Capabilities

### New Capabilities
- `listing-location-preview`: Generate and attach a Google Maps static thumbnail plus formatted address when sending listings to Telegram, with fallbacks and quota safeguards.

### Modified Capabilities
- `telegram-bot-handler`: Extend listing push behavior to include address text and optional map thumbnail, with graceful failure handling.

## Impact
- Telegram bot message composer/formatter and any listing-to-message mapping logic.
- Integration with Google Maps Static Maps API (new dependency, API key config, quota limits).
- Address data source and normalization utilities; possible geocoding lookup if coordinates not stored.
- Media storage/caching for thumbnails (e.g., temp files, CDN, or Telegram file_id reuse).
- CI/tests touching Telegram push formatting; secrets management for API key in local and prod environments.
