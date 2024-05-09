#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import dateparser
import feedparser
from base import PodSync
from loguru import logger
from videogram.utils import delete_files, load_json
from videogram.ytdlp import ytdlp_extract_info


class YouTube(PodSync):
    def __init__(self, name: str, config: dict, database_path: Path) -> None:
        super().__init__(name, config, database_path)

    def check_entry(self, entry: dict) -> dict:
        """Check if the entry is valid for download.

        Some videos may not be valid for download, such as upcoming videos, living videos, banned videos, etc.
        This method checks if the entry is valid for download.

        It should return three keys:
            - need_update_database: bool, whether the database should be updated.
            - metadata: dict, metadata of the entry.
            - need_download: bool, whether the entry should be downloaded.

        For example:
            - For a banned video, the need_update_database should be true because we need to treat it as processed.
              But the need_download should be false because we don't need to download it.
            - For an upcoming video or living video, the need_update_database should be false because we should wait for it to be finished.

        Args:
            entry (dict): A single entry information from the feedparser.

        Returns:
            dict: A dictionary contains the information of the entry.
        """
        res = {
            "need_update_database": False,
            "metadata": {},
            "need_download": False,
        }
        info = ytdlp_extract_info(entry["link"], playlist=False, process=False)[0]
        if info.get("live_status") in {"is_upcoming", "is_live", "post_live"}:
            logger.warning(f"Skip not finished video: {entry['title']}")
            return res

        # log metadata
        video_is_short = info["duration"] <= 60  # YouTube Shorts can be a maximum of 60 seconds long.
        publish_time = dateparser.parse(entry["published"], settings={"TO_TIMEZONE": os.getenv("TZ", "UTC")})
        res["metadata"] = {"title": entry["title"], "vid": entry["yt_videoid"], "shorts": video_is_short, "time": f"{publish_time:%a, %d %b %Y %H:%M:%S %z}"}
        res["need_update_database"] = True

        # skip banned video
        if info.get("availability") == "needs_auth":
            logger.warning(f"Skip banned video: {entry['title']}")
            return res

        # skip YouTube shorts
        if self.config["skip_shorts"] and video_is_short:
            logger.warning(f"Skip shorts: {entry['title']}")
            return res

        logger.warning(f"Found a new video: {entry['title']}")
        res["need_download"] = True
        return res


async def main():
    logger.info(f"Processing {args.name}")

    # initialize youtube
    conf: dict = next(x for x in load_json(args.config) if x["name"] == args.name)
    youtube = YouTube(args.name, conf, Path(args.metadata_dir) / f"{args.name}.json")
    # process feed
    processed_vids = {x["vid"] for x in youtube.database}
    remote = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={conf['yt_channel']}")
    for entry in remote["entries"][::-1]:  # from oldest to latest
        if entry["yt_videoid"] in processed_vids:
            logger.debug(f"Skip processed: {entry['title']}")
            continue
        logger.info(f"New video found: [{entry['yt_videoid']}] {entry['title']}")

        res = await youtube.process_single_entry(entry, use_cookie=False)
        # Update
        youtube.update_database(res["entry_info"])
        if not res["download_info"]:
            continue

        # audio
        if not conf.get("skip_audio", False):
            youtube.upload_files("audio", res["download_info"]["audio_info"], entry["yt_videoid"])
            audio_items = youtube.get_pod_items(
                pod_type="audio",
                info_list=res["download_info"]["audio_info"],
                vid=entry["yt_videoid"],
                entry=entry,
                cover=entry["media_thumbnail"][0]["url"],
            )
            youtube.update_pod_rss("audio", audio_items, feed=remote["feed"])

        # video
        if not conf.get("skip_video", False):
            youtube.upload_files("video", res["download_info"]["video_info"], entry["yt_videoid"])
            video_items = youtube.get_pod_items(
                pod_type="video",
                info_list=res["download_info"]["video_info"],
                vid=entry["yt_videoid"],
                entry=entry,
                cover=entry["media_thumbnail"][0]["url"],
            )
            youtube.update_pod_rss("video", video_items, feed=remote["feed"])
        # Cleanup
        prefix = entry["title"][:60]
        delete_files(Path(".").glob(f"{prefix}.*"))


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Sync YouTube to Telegram")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    parser.add_argument("--config", type=str, default="config/youtube.json", required=False, help="Path to configuration json file.")
    parser.add_argument("--metadata-dir", type=str, default="metadata", required=False, help="Path to metadata directory.")
    parser.add_argument("--name", type=str, required=True, help="Feed name.")
    args = parser.parse_args()

    # loguru settings
    logger.remove()  # Remove default handler.
    logger.add(
        sys.stderr,
        colorize=True,
        level=args.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green>| <level>{level: <7}</level> | <cyan>{name: <10}</cyan>:<cyan>{function: ^30}</cyan>:<cyan>{line: >4}</cyan> - <level>{message}</level>",
    )
    asyncio.run(main())
