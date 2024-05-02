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
from utils import load_xml
from videogram.utils import load_json
from videogram.ytdlp import ytdlp_extract_info


def get_youtube_description(yt_channel: str) -> str:
    info: list[dict] = ytdlp_extract_info(f"https://www.youtube.com/channel/{yt_channel}", playlist=False, process=False)
    return info[0]["description"] if info[0]["description"].strip() else info[0]["uploader"]


def get_new_feeds(pod_type: str) -> tuple[bool, dict]:
    assert pod_type in {"audio", "video"}
    opml_path = f"{pod_type}/podsync.opml"
    opml_data = load_xml(opml_path, template="opml")
    opml_feeds = opml_data["opml"]["body"]["outline"]
    if isinstance(opml_feeds, dict):
        opml_feeds = [opml_feeds]
    exist_feeds = [Path(feed["@xmlUrl"]).stem for feed in opml_feeds]
    logger.debug(f"Found {len(exist_feeds)} existing feeds of {pod_type}")
    conf_feed_names = []
    for conf_file in Path(args.config_path).glob("*.json"):
        conf_data = load_json(conf_file)
        conf_feed_names.extend(x["name"] for x in conf_data)
        for conf in conf_data:
            if conf["name"] in exist_feeds:
                continue

            if yt_channel := conf.get("yt_channel"):  # noqa: SIM108
                description = get_youtube_description(yt_channel)
            else:
                description = conf["title"]

            opml_feeds.append(
                {
                    "@text": description,
                    "@type": "rss",
                    "@xmlUrl": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{pod_type}/{conf['name']}.xml",
                    "@title": conf["title"],
                }
            )
    logger.debug(f"Found {len(conf_feed_names)} config feeds of {pod_type}")
    has_update = set(exist_feeds) != set(conf_feed_names)
    # remove feeds not in configuration any more.
    filtered_feeds = [feed for feed in opml_feeds if Path(feed["@xmlUrl"]).stem in conf_feed_names]
    opml_data["opml"]["body"]["outline"] = sorted(filtered_feeds, key=lambda x: x["@xmlUrl"])
    return has_update, opml_data


def main():
    for pod_type in ["audio", "video"]:
        has_update, new_opml = get_new_feeds(pod_type)
        if has_update:
            logger.info(f"Updating {pod_type} feeds")
            opml_path = f"{pod_type}/podsync.opml"
            with open(opml_path, "w") as f:
                f.write(xmltodict.unparse(new_opml, pretty=True, full_document=True))
            gh.upload_release(opml_path, pod_type)


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Sync YouTube to Telegram")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    parser.add_argument("--config-path", type=str, default="config", required=False, help="Directory path of config json files.")
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
