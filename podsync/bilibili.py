#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import dateparser
import feedparser
from base import PodSync
from loguru import logger
from videogram.utils import delete_files, load_json
from videogram.ytdlp import ytdlp_extract_info
from yt_dlp.utils import DownloadError, YoutubeDLError


class Bilibili(PodSync):
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
        # log metadata
        publish_time = dateparser.parse(entry["published"], settings={"TO_TIMEZONE": os.getenv("TZ", "UTC")})
        res["metadata"] = {"title": entry["title"], "vid": Path(entry["link"]).stem, "time": f"{publish_time:%a, %d %b %Y %H:%M:%S %z}"}
        res["need_update_database"] = True
        try:
            # test if the video is available
            ytdlp_extract_info(entry["link"], use_cookie=True, playlist=False, process=False)[0]
        except DownloadError as e:
            logger.error(f"DownloadError: {e.msg}")
            return res
        except YoutubeDLError as e:
            if "HTTPError 404" in str(e.msg):
                logger.warning(f"Skip deleted video: {entry['title']}")
                return res
            raise
        logger.warning(f"Found a new video: {entry['title']}")
        res["need_download"] = True
        return res


async def main():
    logger.info(f"Processing {args.name}")
    # initialize bilibili
    conf: dict = next(x for x in load_json(args.config) if x["name"] == args.name)
    bilibili = Bilibili(args.name, conf, Path(args.metadata_dir) / f"{args.name}.json")
    # process feed
    processed_vids = {x["vid"] for x in bilibili.database}
    remote = feedparser.parse(f"{os.getenv('RSSHUB_URL', 'https://rsshub.app')}/bilibili/user/video/{conf['uid']}")
    for entry in remote["entries"][::-1]:  # from oldest to latest
        vid = Path(entry["link"]).stem
        if vid in processed_vids:
            logger.debug(f"Skip processed: {entry['title']}")
            continue
        logger.info(f"New video found: [{entry['link']}] {entry['title']}")
        res = await bilibili.process_single_entry(entry)

        # Update
        bilibili.update_database(res["entry_info"])
        if not res["download_info"]:
            continue

        # get cover url
        if re.search(r'img src="(.*)"', entry["summary"]):  # noqa: SIM108
            cover = re.search(r'img src="(.*)"', entry["summary"]).group(1)  # type: ignore
        else:
            cover = conf.get("cover", "")

        # audio
        if not conf.get("skip_audio", False):
            bilibili.upload_files("audio", res["download_info"]["audio_info"], vid)
            audio_items = bilibili.get_pod_items(
                pod_type="audio",
                info_list=res["download_info"]["audio_info"],
                vid=vid,
                entry=entry,
                cover=cover,
            )
            bilibili.update_pod_rss("audio", audio_items, feed=remote["feed"])

        # video
        if not conf.get("skip_video", False):
            bilibili.upload_files("video", res["download_info"]["video_info"], vid)
            video_items = bilibili.get_pod_items(
                pod_type="video",
                info_list=res["download_info"]["video_info"],
                vid=vid,
                entry=entry,
                cover=cover,
            )
            bilibili.update_pod_rss("video", video_items, feed=remote["feed"])
        # Cleanup
        prefix = entry["title"][:60]
        delete_files(Path(".").glob(f"{prefix}.*"))


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Sync Bilibili to Telegram")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    parser.add_argument("--config", type=str, default="config/bilibili.json", required=False, help="Path to mapping json file.")
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
