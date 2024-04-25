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
from yt_dlp.utils import ExtractorError, YoutubeDLError


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
                "item": [],
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
            "@url": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{conf['name']}/{feed_entry['yt_videoid']}.mp4",
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


async def process_single_entry(entry: dict, conf: dict) -> dict:
    res = {
        "meta_has_update": False,
        "item_has_update": False,
        "metadata": {},
        "audio_item": {},
        "video_item": {},
        "item_title": "",
    }
    try:
        yt_info = get_youtube_info(entry["link"])
        if yt_info.get("live_status") != "not_live":
            logger.info(f"Skip not finished video: {entry['title']}")
            return res
        is_short = yt_info["duration"] <= 60  # Short can be a maximum of 60 seconds long.
        res["metadata"] = {"title": entry["title"], "vid": entry["yt_videoid"], "shorts": is_short}
        res["meta_has_update"] = True
        if yt_info.get("availability") == "needs_auth":
            logger.info(f"Skip banned video: {entry['title']}")
            return res
        if is_short and conf["skip_shorts"]:
            logger.info(f"Skip shorts: {entry['title']}")
            return res

        logger.info(f"Downloading {entry['title']}")
        res["item_has_update"] = True
        tg_results = await sync(
            entry["link"],
            tg_id=conf["tg_target"] if conf["tg_target"] else os.environ["DEFAULT_TG_TARGET"],
            sync_video=not conf["skip_video"],
            clean=False,
        )
        res["item_title"] = tg_results["title"]
        if not conf["skip_video"]:
            logger.info(f"Upload video to GitHub: {tg_results['title']}")
            video_path = Path(tg_results["video_path"])
            tg_results["video_filesize"] = video_path.stat().st_size
            vid = entry["yt_videoid"]
            new_path = video_path.with_stem(vid)
            logger.debug(f"Rename {video_path.name} to {new_path.name}")
            video_path.rename(new_path)
            gh.upload_release(new_path.as_posix(), conf["name"], clean=True)
            res["video_item"] = generate_pod_item(conf, entry, tg_results, "video")
        logger.info(f"Upload audio to GitHub: {tg_results['title']}")
        audio_path = Path(tg_results["audio_path"])
        tg_results["audio_filesize"] = audio_path.stat().st_size
        vid = entry["yt_videoid"]
        new_path = audio_path.with_stem(vid)
        logger.debug(f"Rename {audio_path.name} to {new_path.name}")
        audio_path.rename(new_path)
        gh.upload_release(new_path.as_posix(), conf["name"], clean=True)
        res["audio_item"] = generate_pod_item(conf, entry, tg_results, "audio")

    except ExtractorError as e:
        if "IP is likely being blocked" in e.orig_msg:
            logger.error("Ip is blocked by YouTube")
            os._exit(1)
    except YoutubeDLError as e:
        logger.error("YoutubeDLError")
        raise YoutubeDLError from e
    return res


async def main():
    conf: dict = next(x for x in load_json(args.config) if x["name"] == args.name)
    logger.info(f"Processing {args.name}")
    metadata: list = load_json(f"meta/{args.name}.json").get("metadata", [])
    processed_vids = {x["vid"] for x in metadata}
    remote = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={conf['yt_channel']}")
    for entry in remote["entries"][::-1]:  # from oldest to latest
        if entry["yt_videoid"] in processed_vids:
            logger.debug(f"Skip processed: {entry['title']}")
            continue
        logger.warning(f"New video found: [{entry['yt_videoid']}] {entry['title']}")
        res = await process_single_entry(entry, conf)

        if res["meta_has_update"]:
            # save metadata
            Path("meta").mkdir(exist_ok=True)
            metadata.insert(0, res["metadata"])
            save_json({"metadata": metadata}, f"meta/{args.name}.json")
            gh.upload_release(f"meta/{args.name}.json", "metadata")

        if res["item_has_update"]:
            # save audio pod
            Path("audio").mkdir(exist_ok=True)
            pod_header = generate_pod_header(conf, remote["feed"])
            cached_audio = load_xml(f"audio/{args.name}.xml")
            audio_items: list = cached_audio["rss"]["channel"].get("item", [])
            if isinstance(audio_items, dict):
                audio_items = [audio_items]
            audio_items.insert(0, res["audio_item"])
            save_xml(pod_header, audio_items, f"audio/{args.name}.xml")
            gh.upload_release(f"audio/{args.name}.xml", "audio")

            # save video pod
            if not conf["skip_video"]:
                Path("video").mkdir(exist_ok=True)
                cached_video = load_xml(f"video/{args.name}.xml")
                video_items = cached_video["rss"]["channel"].get("item", [])
                if isinstance(video_items, dict):
                    video_items = [video_items]
                video_items.insert(0, res["video_item"])
                save_xml(pod_header, video_items, f"video/{args.name}.xml")
                gh.upload_release(f"video/{args.name}.xml", "video")

            # Cleanup
            prefix = res["item_title"][:60]
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
