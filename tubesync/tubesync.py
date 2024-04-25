#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
from github import gh
from loguru import logger
from utils import load_json, load_xml, save_json, save_xml
from videogram.utils import delete_files
from videogram.videogram import sync
from videogram.youtube import get_youtube_info
from yt_dlp.utils import DownloadError, ExtractorError, YoutubeDLError


def generate_pod_header(conf: dict, feed_info: dict) -> dict:
    pub_date = datetime.strptime(feed_info["published"], "%Y-%m-%dT%H:%M:%S%z")
    now = datetime.now(tz=ZoneInfo("UTC")).strftime("%a, %d %b %Y %H:%M:%S %z")
    return {
        "rss": {
            "@version": "2.0",
            "@xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "channel": {
                "title": feed_info["title"],
                "link": feed_info["link"],
                "description": feed_info["title"],
                "category": "TV & Film",
                "generator": "TubeSync",
                "language": "en-us",
                "lastBuildDate": now,
                "pubDate": pub_date.strftime("%a, %d %b %Y %H:%M:%S %z"),
                "image": {
                    "url": conf["cover"],
                    "title": feed_info["title"],
                    "link": feed_info["link"],
                },
                "itunes:author": feed_info["author"],
                "itunes:block": "yes",
                "itunes:category": {"@text": "TV & Film"},
                "itunes:explicit": "no",
                "itunes:image": {"@href": conf["cover"]},
                "itunes:subtitle": feed_info["title"],
                "itunes:summary": feed_info["title"],
            },
        }
    }


def generate_pod_item(conf: dict, feed_entry: dict, upload_info: dict, pod_type="audio") -> dict:
    pub_date = datetime.strptime(feed_entry["published"], "%Y-%m-%dT%H:%M:%S%z")
    if pod_type == "audio":
        enclosure = {
            "@url": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{conf['name']}/{feed_entry['yt_videoid']}.m4a",
            "@length": upload_info["audio_filesize"],
            "@type": "audio/x-m4a",
        }
    else:
        enclosure = {
            "@url": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{conf['name']}/ncDdI_mC61Y.mp3",
            "@length": upload_info["video_filesize"],
            "@type": "video/mp4",
        }

    return {
        "guid": feed_entry["yt_videoid"],
        "title": feed_entry["title"],
        "link": feed_entry["link"],
        "description": feed_entry["summary"],
        "pubDate": pub_date.strftime("%a, %d %b %Y %H:%M:%S %z"),
        "enclosure": enclosure,
        "itunes:author": feed_entry["author"],
        "itunes:subtitle": feed_entry["title"],
        "itunes:summary": feed_entry["summary"],
        "itunes:image": {"@href": f"https://i.ytimg.com/vi/{feed_entry['yt_videoid']}/maxresdefault.jpg"},
        "itunes:duration": upload_info["duration"],
        "itunes:explicit": "no",
        "itunes:order": "1",
    }


async def main():
    conf: dict = next(x for x in load_json(args.config) if x["name"] == args.name)
    logger.info(f"Processing {args.name}")
    yt_channel = conf["yt_channel"]
    metadata: list = load_json(f"meta/{args.name}.json").get("metadata", [])
    processed_vids = {x["vid"] for x in metadata}
    remote = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_channel}")
    meta_has_update = False
    item_has_update = False
    new_metadata = []
    new_audio_items = []
    new_video_items = []
    try:
        for entry in remote["entries"][::-1]:  # from oldest to latest
            if entry["yt_videoid"] in processed_vids:
                logger.debug(f"Skip processed: {entry['title']}")
                continue
            logger.info(f"New video found: [{entry['yt_videoid']}] {entry['title']}")
            meta_has_update = True
            yt_info = get_youtube_info(entry["link"])
            is_short = yt_info["duration"] <= 60  # Short can be a maximum of 60 seconds long.
            new_metadata.insert(0, {"vid": entry["yt_videoid"], "shorts": is_short})
            if yt_info["availability"] == "needs_auth":
                logger.info(f"Skip banned video: {entry['title']}")
                continue
            if is_short and conf["skip_shorts"]:
                logger.info(f"Skip shorts: {entry['title']}")
                continue

            logger.info(f"Downloading {entry['title']}")
            item_has_update = True
            tg_results = await sync(
                entry["link"],
                tg_id=conf["tg_target"] if conf["tg_target"] else os.environ["DEFAULT_TG_TARGET"],
                sync_video=not conf["skip_video"],
                clean=False,
            )
            if not conf["skip_video"]:
                logger.info(f"Upload video to GitHub: {tg_results['title']}")
                video_path = Path(tg_results["video_path"])
                tg_results["video_filesize"] = video_path.stat().st_size
                vid = entry["yt_videoid"]
                new_path = video_path.with_stem(vid)
                logger.debug(f"Rename {video_path.name} to {new_path.name}")
                video_path.rename(new_path)
                gh.upload_release(new_path.as_posix(), conf["name"])
                new_video_items.insert(0, generate_pod_item(conf, entry, tg_results, "video"))
            logger.info(f"Upload audio to GitHub: {tg_results['title']}")
            audio_path = Path(tg_results["audio_path"])
            tg_results["audio_filesize"] = audio_path.stat().st_size
            vid = entry["yt_videoid"]
            new_path = audio_path.with_stem(vid)
            logger.debug(f"Rename {audio_path.name} to {new_path.name}")
            audio_path.rename(new_path)
            gh.upload_release(new_path.as_posix(), conf["name"])
            new_audio_items.insert(0, generate_pod_item(conf, entry, tg_results, "audio"))
    except ExtractorError as e:
        logger.error(f"ExtractorError: {e}")
    except DownloadError as e:
        logger.error(f"DownloadError: {e}")
    except YoutubeDLError as e:
        logger.error(f"YoutubeDLError: {e}")
        os._exit(1)

    if meta_has_update:
        # save metadata
        new_metadata.extend(metadata)
        Path("new_meta").mkdir(exist_ok=True)
        save_json({"metadata": new_metadata}, f"new_meta/{args.name}.json")
        gh.upload_release(f"new_meta/{args.name}.json", "metadata")

    if item_has_update:
        # save audio pod
        pod_header = generate_pod_header(conf, remote["feed"])
        cached_audio = load_xml(f"audio/{args.name}.xml")
        old_audio_items = cached_audio.get("rss", {}).get("channel", {}).get("item", [])
        Path("new_audio").mkdir(exist_ok=True)
        save_xml(pod_header, old_audio_items, new_audio_items, f"new_audio/{args.name}.xml")
        gh.upload_release(f"new_audio/{args.name}.xml", conf["name"])

        # save video pod
        if not conf["skip_video"]:
            cached_video = load_xml(f"video/{args.name}.xml")
            old_video_items = cached_video.get("rss", {}).get("channel", {}).get("item", [])
            Path("new_video").mkdir(exist_ok=True)
            save_xml(pod_header, old_video_items, new_video_items, f"new_video/{args.name}.xml")
            gh.upload_release(f"new_video/{args.name}.xml", conf["name"])

        # Cleanup
        prefix = tg_results["title"][:60]
        delete_files(Path(".").glob(f"{prefix}.*"))

if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Sync YouTube to Telegram")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    parser.add_argument("--config", type=str, default="config/youtube.json", required=False, help="Path to mapping json file.")
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
