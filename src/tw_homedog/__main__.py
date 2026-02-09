"""Entry point for tw_homedog — Bot mode (default) or CLI mode (--cli)."""

import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from tw_homedog.config import load_config
from tw_homedog.dedup_cleanup import run_cleanup
from tw_homedog.log import setup_logging
from tw_homedog.matcher import find_matching_listings
from tw_homedog.normalizer import normalize_591_listing
from tw_homedog.notifier import send_notifications
from tw_homedog.scraper import scrape_listings, _get_buy_session_headers, enrich_buy_listings
from tw_homedog.storage import Storage

logger = logging.getLogger("tw_homedog")


# =============================================================================
# CLI mode functions (preserved for --cli)
# =============================================================================

def cmd_scrape(config):
    """Scrape 591 and store listings in DB."""
    storage = Storage(config.database_path)
    try:
        raw_listings = scrape_listings(config)
        new_count = 0
        dedup_metrics = {
            "inserted": 0,
            "skipped_duplicate": 0,
            "merged": 0,
            "cleanup_failed": 0,
        }
        batch_cache: dict[str, list[dict]] = {}
        for raw in raw_listings:
            normalized = normalize_591_listing(raw)
            decision = storage.insert_listing_with_dedup(
                normalized,
                batch_cache=batch_cache,
                dedup_enabled=config.dedup.enabled,
                dedup_threshold=config.dedup.threshold,
                price_tolerance=config.dedup.price_tolerance,
                size_tolerance=config.dedup.size_tolerance,
            )
            if decision["inserted"]:
                new_count += 1
                dedup_metrics["inserted"] += 1
            else:
                dedup_metrics["skipped_duplicate"] += 1
        logger.info("Scrape complete: %d new listings stored (out of %d scraped)", new_count, len(raw_listings))
        logger.info(
            "Dedup metrics: inserted=%d skipped_duplicate=%d merged=%d cleanup_failed=%d",
            dedup_metrics["inserted"],
            dedup_metrics["skipped_duplicate"],
            dedup_metrics["merged"],
            dedup_metrics["cleanup_failed"],
        )
        return new_count
    finally:
        storage.close()


def _enrich_matched_listings(config, storage, matched):
    """Enrich matched buy listings that haven't been enriched yet."""
    if config.search.mode != "buy" or not matched:
        return matched

    matched_ids = [m["listing_id"] for m in matched]
    unenriched = storage.get_unenriched_listing_ids(matched_ids)
    if not unenriched:
        logger.info("All matched listings already enriched")
        return matched

    logger.info("Enriching %d unenriched listings...", len(unenriched))
    session, headers = _get_buy_session_headers(config)
    details = enrich_buy_listings(config, session, headers, unenriched, storage=storage)

    for lid, detail in details.items():
        storage.update_listing_detail("591", lid, detail)

    logger.info("Enrichment complete, re-running match...")
    return find_matching_listings(config, storage)


def cmd_notify(config):
    """Match and notify for unnotified listings."""
    storage = Storage(config.database_path)
    try:
        matched = find_matching_listings(config, storage)
        if not matched:
            logger.info("No new matching listings to notify")
            return 0

        matched = _enrich_matched_listings(config, storage, matched)
        if not matched:
            logger.info("No matching listings after enrichment")
            return 0

        sent = asyncio.run(send_notifications(config, storage, matched))
        logger.info("Notification complete: %d sent", sent)
        return sent
    finally:
        storage.close()


def cmd_run(config):
    """Full pipeline: scrape → store → match → notify."""
    logger.info("Starting full pipeline")
    try:
        new_count = cmd_scrape(config)
        logger.info("Scrape phase done: %d new", new_count)
    except Exception as e:
        logger.error("Scrape phase failed: %s", e)
        return 1

    try:
        sent = cmd_notify(config)
        logger.info("Notify phase done: %d sent", sent)
    except Exception as e:
        logger.error("Notify phase failed: %s", e)
        return 1

    logger.info("Pipeline complete")
    return 0


def cmd_dedup_cleanup(
    config,
    *,
    dry_run: bool,
    threshold: float | None,
    price_tolerance: float | None,
    size_tolerance: float | None,
    batch_size: int | None,
):
    """Run historical dedup cleanup."""
    storage = Storage(config.database_path)
    try:
        report = run_cleanup(
            storage,
            dry_run=dry_run,
            threshold=threshold if threshold is not None else config.dedup.threshold,
            price_tolerance=(
                price_tolerance if price_tolerance is not None else config.dedup.price_tolerance
            ),
            size_tolerance=(
                size_tolerance if size_tolerance is not None else config.dedup.size_tolerance
            ),
            batch_size=batch_size if batch_size is not None else config.dedup.cleanup_batch_size,
        )
        logger.info(
            "Dedup cleanup (%s): groups=%d projected=%d merged=%d failed=%d validation=%s",
            "dry-run" if dry_run else "apply",
            report["groups"],
            report["projected_merge_records"],
            report["merged_records"],
            report["cleanup_failed"],
            report.get("validation", {}),
        )
        return 0
    finally:
        storage.close()


# =============================================================================
# CLI mode entry point
# =============================================================================

def cli_main():
    """Original CLI mode entry point."""
    parser = argparse.ArgumentParser(
        prog="tw_homedog",
        description="Taiwan Real Estate Smart Listing Notifier (CLI mode)",
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Full pipeline: scrape → match → notify")
    subparsers.add_parser("scrape", help="Scrape and store listings only")
    subparsers.add_parser("notify", help="Match and send notifications only")
    cleanup_parser = subparsers.add_parser(
        "dedup-cleanup", help="Cleanup historical duplicate listings"
    )
    cleanup_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply cleanup changes (default: dry-run only)",
    )
    cleanup_parser.add_argument("--threshold", type=float, default=None)
    cleanup_parser.add_argument("--price-tolerance", type=float, default=None)
    cleanup_parser.add_argument("--size-tolerance", type=float, default=None)
    cleanup_parser.add_argument("--batch-size", type=int, default=None)

    args = parser.parse_args(sys.argv[2:])  # skip 'cli' from sys.argv

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        sys.exit(1)

    if args.command == "dedup-cleanup":
        result = cmd_dedup_cleanup(
            config,
            dry_run=not args.apply,
            threshold=args.threshold,
            price_tolerance=args.price_tolerance,
            size_tolerance=args.size_tolerance,
            batch_size=args.batch_size,
        )
    else:
        commands = {
            "run": cmd_run,
            "scrape": cmd_scrape,
            "notify": cmd_notify,
        }
        result = commands[args.command](config)

    if args.command == "run" and result != 0:
        sys.exit(result)


# =============================================================================
# Bot mode entry point
# =============================================================================

def bot_main():
    """Bot mode entry point — long-running Telegram Bot process."""
    from tw_homedog.bot import run_bot

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    db_path = os.environ.get("DATABASE_PATH", "data/homedog.db")

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is required (set via environment variable)")
        sys.exit(1)

    if not chat_id:
        logger.error("TELEGRAM_CHAT_ID is required (set via environment variable)")
        sys.exit(1)

    logger.info("Starting tw-homedog Bot mode")
    run_bot(bot_token, chat_id, db_path)


# =============================================================================
# Main entry
# =============================================================================

def main():
    setup_logging(log_dir="logs")

    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        cli_main()
    else:
        bot_main()


if __name__ == "__main__":
    main()
