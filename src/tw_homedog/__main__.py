"""CLI entry point for tw_homedog."""

import argparse
import logging
import sys

from tw_homedog.config import load_config
from tw_homedog.matcher import find_matching_listings
from tw_homedog.normalizer import normalize_591_listing
from tw_homedog.notifier import send_notifications
from tw_homedog.scraper import scrape_listings
from tw_homedog.storage import Storage

logger = logging.getLogger("tw_homedog")


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_scrape(config):
    """Scrape 591 and store listings in DB."""
    storage = Storage(config.database_path)
    try:
        raw_listings = scrape_listings(config)
        new_count = 0
        for raw in raw_listings:
            normalized = normalize_591_listing(raw)
            if storage.insert_listing(normalized):
                new_count += 1
        logger.info("Scrape complete: %d new listings stored (out of %d scraped)", new_count, len(raw_listings))
        return new_count
    finally:
        storage.close()


def cmd_notify(config):
    """Match and notify for unnotified listings."""
    storage = Storage(config.database_path)
    try:
        matched = find_matching_listings(config, storage)
        if not matched:
            logger.info("No new matching listings to notify")
            return 0
        sent = send_notifications(config, storage, matched)
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


def main():
    parser = argparse.ArgumentParser(
        prog="tw_homedog",
        description="Taiwan Real Estate Smart Listing Notifier",
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

    args = parser.parse_args()
    setup_logging()

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        sys.exit(1)

    commands = {
        "run": cmd_run,
        "scrape": cmd_scrape,
        "notify": cmd_notify,
    }
    result = commands[args.command](config)

    if args.command == "run" and result != 0:
        sys.exit(result)


if __name__ == "__main__":
    main()
