## ADDED Requirements

### Requirement: System SHALL detect duplicate real-estate entities before insert
The system SHALL compute a stable dedup fingerprint for each scraped listing and compare it against existing listings and in-batch candidates before inserting into `listings`.

#### Scenario: Duplicate detected against existing DB record
- **WHEN** a newly scraped listing matches an existing listing with a dedup score above the configured threshold
- **THEN** the system MUST skip insertion of the new listing
- **THEN** the system MUST record a dedup decision log containing candidate ids, score, and matched features

#### Scenario: Duplicate detected within same scrape batch
- **WHEN** two listings in the same scrape run match each other above threshold
- **THEN** the system MUST keep only one canonical listing in that batch write path
- **THEN** the duplicate candidate MUST be counted as skipped

### Requirement: System SHALL provide deterministic dedup scoring inputs
The dedup algorithm SHALL use normalized address/location tokens plus numeric tolerance checks (price, size, layout/floor when available) to produce a deterministic score for the same input.

#### Scenario: Address format differs but entity is same
- **WHEN** two listings have equivalent normalized address tokens but different raw title formatting
- **THEN** the dedup score MUST remain stable and exceed threshold if numeric attributes are within tolerance

#### Scenario: Similar area but different property
- **WHEN** two listings share district and similar price range but have low address similarity
- **THEN** the dedup score MUST stay below threshold and both listings MUST be retained

### Requirement: System SHALL clean existing duplicate records safely
The system SHALL support a cleanup process that identifies historical duplicate groups and merges each group into one canonical listing while preserving user-facing state.

#### Scenario: Historical duplicates merged
- **WHEN** cleanup runs and finds a duplicate group
- **THEN** one canonical listing MUST be selected according to configured priority
- **THEN** read/notified/favorite relations from removed records MUST be transferred to canonical listing before deletion

#### Scenario: Dry-run cleanup mode
- **WHEN** cleanup is executed in dry-run mode
- **THEN** no listing rows MUST be deleted or modified
- **THEN** the system MUST output the projected merge groups and counts

### Requirement: System SHALL expose dedup metrics
The pipeline SHALL emit dedup counters for inserted, skipped-as-duplicate, merged, and cleanup-failed items.

#### Scenario: Scrape run summary includes dedup counters
- **WHEN** a scrape+notify pipeline run completes
- **THEN** logs or status output MUST include dedup counter values for that run
