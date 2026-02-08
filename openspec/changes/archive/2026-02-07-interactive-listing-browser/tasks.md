## 1. DB Schema & Storage Layer

- [x] 1.1 Add `listings_read` table to SCHEMA in storage.py, with migration support for existing DBs
- [x] 1.2 Add `mark_as_read(source, listing_id)` method to Storage — inserts or updates read record with current raw_hash
- [x] 1.3 Add `get_unread_matched_listings(config, offset, limit, district_filter)` method to Storage — returns unread listings (no read record OR raw_hash mismatch) that pass matcher filters
- [x] 1.4 Add `get_unread_matched_count(config, district_filter)` method to Storage — returns count of unread matched listings
- [x] 1.5 Add `mark_many_as_read(source, listing_ids)` method to Storage — bulk mark listings as read
- [x] 1.6 Write tests for all new Storage methods (mark_as_read, get_unread, content-change re-unread, mark_many)

## 2. Listing Browser Bot Handlers

- [x] 2.1 Add new ConversationHandler states: LIST_BROWSE, LIST_FILTER
- [x] 2.2 Implement `cmd_list` handler — build config, query unread matched listings page 1, display paginated inline keyboard
- [x] 2.3 Implement `list_page_callback` — handle pagination (list:p:{offset})
- [x] 2.4 Implement `list_filter_callback` — show district filter options and apply filter (list:f:{code})
- [x] 2.5 Implement `list_detail_callback` — show full listing detail, auto-mark as read (list:d:{listing_id})
- [x] 2.6 Implement `list_back_callback` — return to list from detail view (list:back)
- [x] 2.7 Implement `list_mark_read_callback` — mark single listing as read from detail (list:r:{listing_id})
- [x] 2.8 Implement `list_mark_all_read_callback` — mark all current results as read (list:ra)
- [x] 2.9 Register /list command and all list callbacks in Bot Application
- [x] 2.10 Write tests for list command and callback handlers

## 3. Pipeline Notification Change

- [x] 3.1 Modify `_run_pipeline` in bot.py — replace `send_notifications()` call with unread count summary message
- [x] 3.2 Modify `_scheduled_pipeline` — send summary with /list hint instead of individual messages
- [x] 3.3 Update `/status` to show unread matched count instead of unnotified count
- [x] 3.4 Update returning user `/start` welcome message to include /list command
- [x] 3.5 Write tests for updated pipeline notification behavior

## 4. Integration & Cleanup

- [x] 4.1 Update existing notifier tests to reflect new summary behavior
- [x] 4.2 Run full test suite, fix any regressions
- [x] 4.3 Update CLAUDE.md with /list command documentation
