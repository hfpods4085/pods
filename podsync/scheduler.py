#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import feedparser
from github import gh
from loguru import logger
from videogram.utils import load_json


def main():
    if not Path(args.config).exists():
        return

    if args.platform == "youtube":
        check_youtube()
    elif args.platform == "bilibili":
        check_bilibili()
    else:
        raise NotImplementedError


def check_youtube():
    configs = load_json(args.config)
    for conf in configs:
        logger.info(f"Processing {conf['title']}")
        database: list = load_json(f"{args.metadata_dir}/{conf['name']}.json", default=[])  # type: ignore
        processed_vids = {x["vid"] for x in database}
        remote = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={conf['yt_channel']}")
        remote_vids = {x["yt_videoid"] for x in remote["entries"]}
        if remote_vids.issubset(processed_vids):
            logger.info(f"No new videos found for {conf['title']}")
            continue
        logger.warning(f"New videos found for {conf['title']}, trigger an update.")
        gh.trigger_workflow(conf["name"], platform="youtube")


def check_bilibili():
    configs = load_json(args.config)

    for conf in configs:
        logger.info(f"Processing {conf['title']}")
        database: list = load_json(f"{args.metadata_dir}/{conf['name']}.json", default=[])  # type: ignore
        processed_vids = {x["vid"] for x in database}
        remote = feedparser.parse(f"{os.getenv('RSSHUB_URL', 'https://rsshub.app')}/bilibili/user/video/{conf['uid']}")
        remote_vids = {Path(x["link"]).stem for x in remote["entries"][:5]}
        if remote_vids.issubset(processed_vids):
            logger.info(f"No new videos found for {conf['title']}")
            continue
        logger.warning(f"New videos found for {conf['title']}, trigger an update.")
        gh.trigger_workflow(conf["name"], platform="bilibili")


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Sync YouTube to Telegram")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    parser.add_argument("--metadata-dir", type=str, default="metadata", required=False, help="Path to metadata directory.")
    parser.add_argument("--config", type=str, default="config/youtube.json", required=False, help="Path to mapping json file.")
    parser.add_argument("--platform", type=str, default="youtube", required=False, help="Social media platform.")
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
