## ADDED Requirements

### Requirement: Config table schema
The system SHALL store configuration in a `bot_config` table with `key TEXT PRIMARY KEY` and `value TEXT` columns. Values MUST be JSON-serialized.

#### Scenario: Table creation
- **WHEN** Storage initializes
- **THEN** `bot_config` table is created if not exists

#### Scenario: Store simple value
- **WHEN** system sets key "search.mode" to "buy"
- **THEN** row is upserted with key="search.mode", value='"buy"'

#### Scenario: Store complex value
- **WHEN** system sets key "search.districts" to ["Daan", "Xinyi"]
- **THEN** row is upserted with key="search.districts", value='["Daan", "Xinyi"]'

### Requirement: Config read with defaults
The system SHALL provide a method to read config values with fallback defaults. Missing keys MUST return the specified default.

#### Scenario: Read existing key
- **WHEN** system reads key "search.mode" and it exists
- **THEN** returns the deserialized value "buy"

#### Scenario: Read missing key with default
- **WHEN** system reads key "search.min_ping" and it does not exist
- **THEN** returns the provided default value

### Requirement: Config to Config dataclass conversion
The system SHALL provide a method to build the existing `Config` dataclass from DB values. This MUST be compatible with all existing pipeline modules.

#### Scenario: Build Config from DB
- **WHEN** system calls `build_config()` on DbConfig
- **THEN** returns a fully populated `Config` dataclass using DB values, with defaults for missing optional fields

#### Scenario: Incomplete config
- **WHEN** required fields (region, districts, price, bot_token, chat_id) are missing
- **THEN** raises `ValueError` listing missing fields

### Requirement: YAML config migration
The system SHALL provide a method to import settings from an existing `config.yaml` into the DB config.

#### Scenario: Successful migration
- **WHEN** user triggers migration with a valid config.yaml path
- **THEN** all settings are written to bot_config table and success is confirmed

#### Scenario: Migration with existing config
- **WHEN** DB already has config values and migration is triggered
- **THEN** system asks for confirmation before overwriting, or merges only missing keys

### Requirement: Atomic config updates
The system SHALL wrap multi-key config updates in a transaction. Partial updates MUST NOT occur.

#### Scenario: Multi-key update
- **WHEN** system updates districts and mode together
- **THEN** both values are committed in a single transaction

#### Scenario: Failed update
- **WHEN** a write error occurs during multi-key update
- **THEN** all changes in the transaction are rolled back
