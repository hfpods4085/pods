#! /usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import sys
from pathlib import Path

from github import gh
from loguru import logger
from utils import load_xml, save_xml
from videogram.utils import load_json, save_json


def delete_old_assets(assets: dict[str, dict], keep: int = 20):
    sorted_assets = sorted(assets.items(), key=lambda x: x[1]["updated_at"], reverse=True)
    for name, asset in sorted_assets[keep:]:
        if Path(name).suffix in {".mp4", ".m4a", ".mp3"}:
            logger.info(f"Delete {args.name}: {name}")
            gh.delete_asset(asset["id"])


def delete_old_podcast_items(keep: int = 20):
    # metadata
    metadata_path = Path(args.metadata_dir) / f"{args.name}.json"
    metadata: list[dict] = load_json(metadata_path, default=[])  # type: ignore
    if len(metadata) > keep:
        for item in metadata[keep:]:
            logger.info(f"Delete {args.name}: {item['title']}")
            metadata.remove(item)
        save_json(metadata, metadata_path)
        gh.upload_release(metadata_path, args.metadata_dir)
    else:
        logger.info(f"No need to delete metadata of {args.name}")

    # audio and video
    for pod_type in ["audio", "video"]:
        xml_path = Path(f"{pod_type}/{args.name}.xml")
        xml = load_xml(xml_path)
        items = xml["rss"]["channel"].get("item", [])
        if isinstance(items, dict):
            items = [items]
        if len(items) > keep:
            for item in items[keep:]:
                logger.info(f"Delete {args.name} {pod_type}: {item['title']}")
                items.remove(item)
            save_xml(xml, items, xml_path)
            gh.upload_release(xml_path, pod_type)


def main():
    configs = [x for x in load_json(args.config) if x["name"] == args.name]
    config: dict = configs[0] if configs else {}
    delete_old_podcast_items(args.keep)
    keep = args.keep if config.get("skip_audio") or config.get("skip_video") else args.keep * 2
    assets = gh.get_release_assets(args.name)
    delete_old_assets(assets, keep)


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Clenup old podcasts")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    parser.add_argument("--config", type=str, default="config/youtube.json", required=False, help="Path to configuration json file.")
    parser.add_argument("--name", type=str, required=True, help="Feed name.")
    parser.add_argument("--metadata-dir", type=str, default="metadata", required=False, help="Path to metadata directory.")
    parser.add_argument("--keep", type=int, default=20, required=False, help="How many assets to keep")
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
