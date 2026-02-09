## ADDED Requirements

### Requirement: Generate map thumbnail for listing pushes
The system SHALL generate a static map image centered on the listing location when preparing a Telegram listing push, using stored coordinates when present or a geocoded address otherwise. The image SHALL include a marker indicating the location and respect configured size/style parameters.

#### Scenario: Map generated from coordinates
- **WHEN** a listing has stored latitude/longitude
- **THEN** the system builds a static map URL with those coordinates and fetches a thumbnail image within configured timeout
- **THEN** the thumbnail is returned for attachment to the Telegram push

#### Scenario: Map generated from address
- **WHEN** a listing lacks coordinates but has a complete address
- **THEN** the system geocodes the address once, caches the result, and uses the coordinates to build/fetch a static map thumbnail
- **THEN** the thumbnail is returned for attachment to the Telegram push

### Requirement: Graceful fallback when map unavailable
The system SHALL continue sending the Telegram listing push even if map generation fails (invalid address, geocoding failure, API quota, timeout, or download error).

#### Scenario: Map generation failure
- **WHEN** the static map request returns an error or times out
- **THEN** the system logs the error, increments a metric, and proceeds to send the listing push without a map image
- **THEN** the listing push still includes the formatted address text

#### Scenario: Missing address data
- **WHEN** a listing has neither coordinates nor a complete address
- **THEN** the system skips map generation and sends the listing push with address omitted or marked as unavailable

### Requirement: Cache and reuse map assets
The system SHALL minimize duplicate map fetches by caching thumbnails per listing+address hash and reusing Telegram `file_id` when available to avoid re-uploading identical images.

#### Scenario: Cached thumbnail reused
- **WHEN** a listing push is prepared for a listing whose map thumbnail was generated previously and the address hash is unchanged within cache TTL
- **THEN** the system skips external map fetch and reuses the cached image or Telegram `file_id` for the push
