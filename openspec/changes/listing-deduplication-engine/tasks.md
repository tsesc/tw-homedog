## 1. Schema & Data Foundations

- [x] 1.1 Add DB migration for dedup fields/indexes (e.g., `entity_fingerprint`) and any helper mapping table needed for merge/audit
- [x] 1.2 Add storage APIs to query dedup candidates by fingerprint and to merge duplicate groups inside one transaction
- [x] 1.3 Add audit persistence for dedup decisions (skipped/merged records with reason and score)

## 2. Dedup Algorithm

- [x] 2.1 Implement address/feature normalization utility for stable dedup inputs
- [x] 2.2 Implement deterministic dedup scoring (address similarity + price/size/layout tolerance)
- [x] 2.3 Define canonical-selection policy for duplicate groups (completeness/recency/linked-state priority)
- [x] 2.4 Unit-test score thresholds and canonical selection with representative duplicate/non-duplicate samples

## 3. Ingestion Path Integration

- [x] 3.1 Integrate dedup check into scrape insert path (DB existing + same-batch memory cache)
- [x] 3.2 Skip insert when score exceeds threshold and emit dedup skip logs/counters
- [x] 3.3 Ensure normal insert path still works for non-duplicates and updates fingerprint columns
- [x] 3.4 Add integration tests verifying duplicate listings from different broker IDs are skipped

## 4. Historical Cleanup

- [x] 4.1 Implement cleanup command/service with dry-run mode that outputs projected merge groups
- [x] 4.2 Implement apply mode to merge duplicates and transfer `notifications_sent`, `listings_read`, and `favorites` relations
- [x] 4.3 Add post-cleanup validation queries/assertions to detect orphaned relations
- [x] 4.4 Add rollback-safe execution guidance (batch size, transaction boundaries, failure handling)

## 5. Observability & Rollout

- [x] 5.1 Add run-level dedup metrics (`inserted`, `skipped_duplicate`, `merged`, `cleanup_failed`)
- [x] 5.2 Document tuning knobs (threshold/tolerance), dry-run procedure, and operations playbook
- [x] 5.3 Run dry-run on production-like DB snapshot and review false-positive/false-negative samples
- [x] 5.4 Enable dedup in production, monitor logs/counters, and iterate threshold if needed
