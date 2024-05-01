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
from github import gh
from loguru import logger
from podcast import generate_pod_header, generate_pod_item
from utils import load_json, load_xml, save_json, save_xml
from videogram.utils import delete_files
from videogram.videogram import sync
from videogram.ytdlp import ytdlp_extract_info


class YouTube:
    def __init__(self, name: str, config: dict, metadata_dir: str) -> None:
        self.name = name
        self.config = config
        self.metadata_dir = metadata_dir
        self.metadata: list = load_json(f"{metadata_dir}/{name}.json").get("metadata", [])

    def parse_entry_info(self, entry: dict) -> dict:
        res = {
            "need_update_metadata": False,
            "metadata": {},
            "need_download": False,
        }
        info = ytdlp_extract_info(entry["link"], playlist=False, process=False)[0]
        if info.get("live_status") in {"is_upcoming", "is_live", "post_live"}:
            logger.warning(f"Skip not finished video: {entry['title']}")
            return res

        # log metadata
        video_is_short = info["duration"] <= 60  # YouTube Shorts can be a maximum of 60 seconds long.
        res["metadata"] = {"title": entry["title"], "vid": entry["yt_videoid"], "shorts": video_is_short}
        res["need_update_metadata"] = True

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

    async def process_single_entry(self, entry: dict) -> dict:
        res = {
            "entry_info": {},
            "download_info": {},
        }
        entry_info = self.parse_entry_info(entry)
        if not entry_info["need_update_metadata"]:
            res["entry_info"] = entry_info
            return res
        publish_time = dateparser.parse(entry["published"], settings={"TO_TIMEZONE": os.getenv("TZ", "UTC")})
        entry_info["metadata"]["time"] = f"{publish_time:%a, %d %b %Y %H:%M:%S %z}"
        res["entry_info"] = entry_info
        if not entry_info["need_download"]:
            return res
        logger.info(f"Syncing to Telegram: {entry['title']}")
        tg_target = self.config["tg_target"] if self.config["tg_target"] else os.environ["DEFAULT_TG_TARGET"]
        download_info = await sync(entry["link"], tg_id=tg_target, sync_video=not self.config["skip_video"], clean=False)
        res["download_info"] = download_info
        return res

    def update_metadata(self, entry_info: dict) -> None:
        if entry_info["need_update_metadata"]:
            Path(self.metadata_dir).mkdir(exist_ok=True)
            self.metadata.insert(0, entry_info["metadata"])
            save_json({"metadata": self.metadata}, f"{self.metadata_dir}/{self.name}.json")
            gh.upload_release(f"{self.metadata_dir}/{self.name}.json", "metadata")

    def update_audio_feed(self, download_info: dict, feed_entry: dict, feed_info: dict) -> None:
        if len(download_info["audio_info"]) == 0:
            return

        audio = download_info["audio_info"][0]
        logger.info(f"Upload audio to GitHub: {audio['title']}")
        audio_path = Path(audio["audio_path"])
        file_size = audio_path.stat().st_size
        vid = feed_entry["yt_videoid"]
        new_path = audio_path.with_stem(vid)
        logger.debug(f"Rename {audio_path.name} to {new_path.name}")
        audio_path.rename(new_path)
        gh.upload_release(new_path.as_posix(), self.name, clean=True)
        pod_item = generate_pod_item(feed_entry, "audio", self.name, file_size, audio["duration"])

        # upload audio pod
        Path("audio").mkdir(exist_ok=True)
        cached_audio = load_xml(f"audio/{self.name}.xml")
        audio_items = cached_audio["rss"]["channel"].get("item", [])
        if isinstance(audio_items, dict):
            audio_items = [audio_items]

        audio_items.insert(0, pod_item)
        pod_header = generate_pod_header(feed_info, cover_url=self.config["cover"])
        save_xml(pod_header, audio_items, f"audio/{self.name}.xml")
        gh.upload_release(f"audio/{self.name}.xml", "audio")

    def update_video_feed(self, download_info: dict, feed_entry: dict, feed_info: dict) -> None:
        if len(download_info["video_info"]) == 0:
            return

        pod_items = []
        for idx, video in enumerate(download_info["video_info"]):
            logger.info(f"Upload video to GitHub: {video['title']}")
            video_path = Path(video["video_path"])
            file_size = video_path.stat().st_size
            vid = feed_entry["yt_videoid"]
            # we append P{idx+1} to the filename if it's a splited video
            new_path = video_path.with_stem(f"{vid}-P{idx+1}") if idx > 0 else video_path.with_stem(vid)
            logger.debug(f"Rename {video_path.name} to {new_path.name}")
            video_path.rename(new_path)
            gh.upload_release(new_path.as_posix(), self.name, clean=True)

            # save video pod
            pod_item = generate_pod_item(feed_entry, "video", self.name, file_size, video["duration"])
            if idx == 0:
                pod_items.append(pod_item)
            else:
                # revise pod item for splited video
                pod_item["guid"] = f"{pod_item['guid']}-P{idx+1}"
                pod_item["title"] = f"{pod_item['title']}-P{idx+1}"
                enclosure_url = pod_item["enclosure"]["@url"]
                pod_item["enclosure"]["@url"] = Path(enclosure_url).with_stem(f"{vid}-P{idx+1}").as_posix()
                pod_items.append(pod_item)

        Path("video").mkdir(exist_ok=True)
        cached_video = load_xml(f"video/{self.name}.xml")
        video_items = cached_video["rss"]["channel"].get("item", [])
        if isinstance(video_items, dict):
            video_items = [video_items]
        pod_items.extend(video_items)

        pod_header = generate_pod_header(feed_info, cover_url=self.config["cover"])
        save_xml(pod_header, pod_items, f"video/{self.name}.xml")
        gh.upload_release(f"video/{self.name}.xml", "video")


async def main():
    logger.info(f"Processing {args.name}")

    # initialize youtube
    conf: dict = next(x for x in load_json(args.config) if x["name"] == args.name)
    youtube = YouTube(args.name, conf, args.metadata_dir)
    # process feed
    processed_vids = {x["vid"] for x in youtube.metadata}
    remote = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={conf['yt_channel']}")
    for entry in remote["entries"][::-1]:  # from oldest to latest
        if entry["yt_videoid"] in processed_vids:
            logger.debug(f"Skip processed: {entry['title']}")
            continue
        logger.info(f"New video found: [{entry['yt_videoid']}] {entry['title']}")

        res = await youtube.process_single_entry(entry)

        # Update
        youtube.update_metadata(res["entry_info"])
        if res["download_info"]:
            youtube.update_audio_feed(res["download_info"], feed_entry=entry, feed_info=remote["feed"])
            youtube.update_video_feed(res["download_info"], feed_entry=entry, feed_info=remote["feed"])

        # Cleanup
        if res["entry_info"]["need_download"]:
            prefix = res["entry_info"]["metadata"]["title"][:60]
            delete_files(Path(".").glob(f"{prefix}.*"))


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Sync YouTube to Telegram")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    parser.add_argument("--config", type=str, default="config/youtube.json", required=False, help="Path to mapping json file.")
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
