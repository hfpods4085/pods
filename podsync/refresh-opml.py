#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import xmltodict
from github import gh
from loguru import logger
from utils import load_json, load_xml


def has_update(conf_data: dict, opml_data: dict) -> bool:
    conf_feed_names = {info["name"] for info in conf_data}
    opml_feeds = opml_data["opml"]["body"]["outline"]
    opml_feed_names = {Path(feed["@xmlUrl"]).stem for feed in opml_feeds}
    return conf_feed_names != opml_feed_names


def update_opml(conf_data: dict, opml_data: dict, pod_type: str) -> dict:
    opml_feeds = opml_data["opml"]["body"]["outline"]
    exist_feeds = [Path(feed["@xmlUrl"]).stem for feed in opml_feeds]
    new_feeds = []
    for info in conf_data:
        if Path(info["name"]).stem in exist_feeds:
            new_feeds.append(next(feed for feed in opml_feeds if Path(feed["@xmlUrl"]).stem == info["name"]))
            continue
        new_feeds.append(
            {
                "@text": f"{info['title']}&#10;官方频道: https://www.youtube.com/channel/{info['yt_channel']}",
                "@type": "rss",
                "@xmlUrl": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{pod_type}/{info['name']}.xml",
                "@title": info["title"],
            }
        )
    opml_data["opml"]["body"]["outline"] = new_feeds
    return opml_data


def main():
    conf_data = load_json(args.config)
    for pod_type in ["audio", "video"]:
        opml_path = f"{pod_type}/podsync.opml"
        opml_data = load_xml(opml_path, template="opml")
        if has_update(conf_data, opml_data):
            logger.info(f"Updating {pod_type} opml file.")
            new_opml = update_opml(conf_data, opml_data, pod_type)
            with open(opml_path, "w") as f:
                f.write(xmltodict.unparse(new_opml, pretty=True, full_document=True))
            gh.upload_release(opml_path, pod_type)


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
