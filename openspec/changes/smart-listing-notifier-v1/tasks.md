## 1. Project Setup

- [x] 1.1 Initialize Python project with uv (pyproject.toml, .python-version)
- [x] 1.2 Create `tw_homedog` package structure (src layout with __init__.py, __main__.py)
- [x] 1.3 Add core dependencies: playwright, requests, beautifulsoup4, python-telegram-bot, pyyaml
- [x] 1.4 Create config.example.yaml with all configurable fields and comments
- [x] 1.5 Add .gitignore (db files, config.yaml, __pycache__, .venv)

## 2. Config Manager

- [x] 2.1 Implement YAML config loader with file path resolution (default: config.yaml, --config override)
- [x] 2.2 Implement config schema validation (required fields, type checking)
- [x] 2.3 Write tests for config loading: valid config, missing file, invalid YAML, missing required fields

## 3. Data Storage (SQLite)

- [x] 3.1 Implement database initialization (create tables: listings, notifications_sent)
- [x] 3.2 Implement listing insert with deduplication (source + listing_id, content_hash fallback)
- [x] 3.3 Implement notification history tracking (record sent, check if already notified)
- [x] 3.4 Write tests for storage: init, insert, dedup, notification tracking

## 4. Data Normalizer

- [x] 4.1 Implement 591 raw data to unified listing format converter
- [x] 4.2 Implement price extraction from various Chinese/numeric formats
- [x] 4.3 Implement SHA256 content hash generation (title + price + address)
- [x] 4.4 Write tests for normalizer: full conversion, missing fields, price parsing, hash generation

## 5. Scraper (591)

- [x] 5.1 Implement Playwright-based listing ID collector (search page → listing IDs)
- [x] 5.2 Implement HTTP-based listing detail extractor (reuse/adapt base repo logic)
- [x] 5.3 Implement anti-detection: random delay (2-5s), User-Agent rotation, retry with backoff
- [x] 5.4 Implement configurable search parameters (region, districts, price, area, max pages)
- [x] 5.5 Write tests for scraper: mock HTML parsing, parameter generation, retry logic

## 6. Match Engine

- [x] 6.1 Implement price range filter (min/max, open-ended)
- [x] 6.2 Implement district filter
- [x] 6.3 Implement size (ping) filter
- [x] 6.4 Implement keyword filter (include ALL / exclude ANY)
- [x] 6.5 Implement composite matcher (combine all filters, skip already-notified)
- [x] 6.6 Write tests for matcher: each filter individually, combined filters, edge cases

## 7. Telegram Notifier

- [x] 7.1 Implement Telegram Bot message sender with formatted listing template
- [x] 7.2 Implement bot token validation on startup
- [x] 7.3 Implement rate limiting (1s between messages, max 10 per batch)
- [x] 7.4 Implement send failure handling (log error, don't mark as notified)
- [x] 7.5 Write tests for notifier: message formatting, rate limiting, error handling (mock API)

## 8. CLI & Pipeline

- [x] 8.1 Implement `__main__.py` with argparse: subcommands `run`, `scrape`, `notify` + `--config` flag
- [x] 8.2 Implement `run` command: full pipeline (scrape → normalize → store → match → notify)
- [x] 8.3 Implement `scrape` command: scrape + store only
- [x] 8.4 Implement `notify` command: match + notify only
- [x] 8.5 Implement graceful error handling (partial failure continues, proper exit codes)

## 9. Integration & Deployment

- [x] 9.1 End-to-end integration test with mock 591 responses
- [x] 9.2 Create Dockerfile (uv-based, per CLAUDE.md Python standards)
- [x] 9.3 Create cron setup instructions in README
- [x] 9.4 Verify full pipeline: config → scrape → store → match → notify
