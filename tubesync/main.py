#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys

import feedparser
from github import gh
from loguru import logger
from utils import load_json


def main():
    configs = load_json(args.config)

    for conf in configs:
        logger.info(f"Processing {conf['name']}")
        metadata: list = load_json(f"meta/{conf['name']}.json").get("metadata", [])
        processed_vids = {x["vid"] for x in metadata}
        remote = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={conf['yt_channel']}")
        remote_vids = {x["yt_videoid"] for x in remote["entries"]}
        if remote_vids.issubset(processed_vids):
            logger.info(f"No new videos found for {conf['name']}")
            continue
        logger.warning(f"New videos found for {conf['name']}, trigger an update.")
        gh.trigger_workflow(conf["name"])


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Sync YouTube to Telegram")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    parser.add_argument("--config", type=str, default="config/youtube.json", required=False, help="Path to mapping json file.")
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
