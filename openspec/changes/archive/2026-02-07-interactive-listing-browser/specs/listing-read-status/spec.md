## ADDED Requirements

### Requirement: Read status tracking table
The system SHALL maintain a `listings_read` table in SQLite to track which listings the user has read. The table SHALL store source, listing_id, the raw_hash at time of reading, and a timestamp.

#### Scenario: Table creation
- **WHEN** the application starts and initializes the database
- **THEN** the `listings_read` table is created if it does not exist, with columns: source (TEXT), listing_id (TEXT), raw_hash (TEXT), read_at (TEXT), and PRIMARY KEY on (source, listing_id)

### Requirement: Mark listing as read
The system SHALL provide a method to mark a listing as read, recording the listing's current raw_hash. If the listing is already marked as read, the raw_hash and read_at SHALL be updated.

#### Scenario: Mark new listing as read
- **WHEN** a listing is marked as read for the first time
- **THEN** system inserts a record with source, listing_id, current raw_hash from listings table, and current timestamp

#### Scenario: Re-mark already read listing
- **WHEN** a listing that is already read is marked as read again
- **THEN** system updates the existing record with new raw_hash and timestamp

### Requirement: Unread detection with content change awareness
The system SHALL consider a listing as "unread" if it has no read record OR if the listing's current raw_hash differs from the read record's raw_hash. This ensures updated listings resurface for the user.

#### Scenario: Listing never read
- **WHEN** a listing has no record in listings_read
- **THEN** the listing is considered unread

#### Scenario: Listing read and unchanged
- **WHEN** a listing has a read record AND listings.raw_hash equals listings_read.raw_hash
- **THEN** the listing is considered read and SHALL be excluded from unread queries

#### Scenario: Listing read but content updated
- **WHEN** a listing has a read record BUT listings.raw_hash differs from listings_read.raw_hash
- **THEN** the listing is considered unread (content has changed since last read)

### Requirement: Query unread matched listings
The system SHALL provide a method to retrieve unread listings that also pass matcher filters, supporting pagination and optional district filter.

#### Scenario: Get unread matched listings
- **WHEN** system queries for unread matched listings with offset=0, limit=5
- **THEN** system returns up to 5 listings that are unread (per content-aware logic) and match current search config filters

#### Scenario: Get unread matched listings with district filter
- **WHEN** system queries for unread matched listings with district="大安區"
- **THEN** system returns only unread matched listings in 大安區

#### Scenario: Get total unread matched count
- **WHEN** system queries for total count of unread matched listings
- **THEN** system returns the count without loading full listing data
