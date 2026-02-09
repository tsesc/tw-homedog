## ADDED Requirements

### Requirement: Parallel region scraping
The system SHALL scrape multiple regions concurrently using ThreadPoolExecutor when more than one region is configured. Each region SHALL execute in its own thread with an independent Playwright session and requests.Session.

#### Scenario: Multiple regions scraped in parallel
- **WHEN** config contains 2 or more regions
- **THEN** the system submits each region's scrape task to a thread pool and collects results concurrently
- **THEN** the combined listing results are equivalent to sequential execution (same data, order may differ)

#### Scenario: Single region falls back to direct execution
- **WHEN** config contains exactly 1 region
- **THEN** the system executes scraping directly without thread pool overhead

#### Scenario: One region fails without affecting others
- **WHEN** scraping one region raises an exception (network error, session failure, etc.)
- **THEN** the system logs the error for that region
- **THEN** the system returns listings from all other regions that succeeded

### Requirement: Thread-safe progress reporting
The system SHALL ensure progress callbacks from concurrent threads do not interleave or corrupt each other.

#### Scenario: Concurrent progress callbacks
- **WHEN** multiple regions report progress simultaneously
- **THEN** each callback invocation completes atomically (no interleaved messages)

### Requirement: Configurable worker limit
The system SHALL limit the number of concurrent scraping threads to avoid excessive resource usage.

#### Scenario: Worker count bounded
- **WHEN** the number of configured regions exceeds the maximum worker limit (4)
- **THEN** the system uses at most 4 concurrent workers, queueing remaining regions
