## 1. Setup

- [x] 1.1 Add Google Maps Static Maps (and Geocoding if needed) configuration: env vars for API key, base URL, style, cache TTL, feature flag default off
- [x] 1.2 Add any required client/dependency for HTTP requests and image handling if not already present; document install in requirements

## 2. Map Thumbnail Generation

- [x] 2.1 Implement address normalization + optional single-shot geocode to obtain coords when missing
- [x] 2.2 Implement static map URL builder with size/zoom/marker defaults and signing if required
- [x] 2.3 Implement fetch + caching layer (address-hash key, TTL) and optional reuse of Telegram `file_id`
- [x] 2.4 Add timeouts/error handling paths returning text-only fallback while logging/metric counts
- [x] 2.5 Unit tests for URL builder, geocode fallback, and cache reuse logic

## 3. Telegram Push Integration

- [x] 3.1 Update listing push composer to request map thumbnail and address; attach image when available
- [x] 3.2 Ensure caption/text includes formatted address and still renders correctly with/without map thumbnail
- [x] 3.3 Handle missing/invalid data gracefully (no crash, send without map)
- [x] 3.4 Reuse Telegram `file_id` for repeated sends when available

## 4. Observability & Release

- [x] 4.1 Add metrics/logging for map requests, cache hits, failures, and quota responses
- [x] 4.2 Add configuration docs and examples for staging/prod; note quota/latency considerations
- [ ] 4.3 Manual validation in staging: listing with coords, listing with address-only, listing missing address
- [ ] 4.4 Flip feature flag on per channel once validation passes; add rollback switch verification
