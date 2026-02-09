## ADDED Requirements

### Requirement: Listing push includes address text and map thumbnail when available
The bot SHALL enrich listing push messages with the property's formatted address and attach the map thumbnail provided by the location preview component when available.

#### Scenario: Map thumbnail available
- **WHEN** a listing push is prepared and a map thumbnail + address are provided
- **THEN** the bot attaches the map image (or Telegram file_id) as part of the push
- **THEN** the push caption/text includes the formatted address ahead of other listing details

#### Scenario: Map thumbnail unavailable
- **WHEN** a listing push is prepared but no map thumbnail is available
- **THEN** the bot sends the listing push without an image attachment for the map
- **THEN** the push still includes the formatted address text if present, otherwise omits address gracefully
