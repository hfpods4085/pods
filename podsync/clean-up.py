#! /usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import sys
from pathlib import Path

from github import gh
from loguru import logger


def delete_old_assets(assets: dict[str, dict], keep: int = 40):
    sorted_assets = sorted(assets.items(), key=lambda x: x[1]["updated_at"], reverse=True)
    for name, asset in sorted_assets[keep:]:
        if Path(name).suffix in {".mp4", ".m4a", ".mp3"}:
            logger.info(f"Delete {name}")
            gh.delete_asset(asset["id"])


def main():
    logger.debug("Fetching releases")
    releases = gh.get_releases()
    for name in releases:
        logger.info(f"Processing {name}")
        assets = gh.get_release_assets(name)
        delete_old_assets(assets)


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Sync YouTube to Telegram")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    args = parser.parse_args()

    # loguru settings
    logger.remove()  # Remove default handler.
    logger.add(
        sys.stderr,
        colorize=True,
        level=args.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green>| <level>{level: <7}</level> | <cyan>{name: <10}</cyan>:<cyan>{function: ^30}</cyan>:<cyan>{line: >4}</cyan> - <level>{message}</level>",
    )
    main()
