#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

from github import gh
from loguru import logger
from podcast import generate_pod_header, generate_pod_item
from utils import load_xml, save_xml
from videogram.utils import load_json, save_json
from videogram.videogram import sync


class PodSync:
    """Base class for preprocessing."""

    def __init__(self, name: str, config: dict, database_path: Path) -> None:
        """Initialize PodSync.

        Args:
            name (str): feed name
            config (dict): sync configuration of this feed.
            database_path (Path): Path of the database, which  processed videos of this feed.
        """
        self.name = name
        self.config = config
        self.db_path = database_path
        self.database: list[dict] = load_json(database_path.as_posix(), default=[])  # type: ignore

    def check_entry(self, entry: dict) -> dict:
        """Check if the entry is valid for download.

        This method should be implemented by the subclass.

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
        raise NotImplementedError

    async def process_single_entry(self, entry: dict) -> dict:
        """Process a single entry.

        Args:
            entry (dict): A single entry information from the feedparser.

        Returns:
            dict: A dictionary contains the processed information of the entry.
        """
        res = {
            "entry_info": {},
            "download_info": {},
        }
        checked_entry_result = self.check_entry(entry)
        res["entry_info"] = checked_entry_result
        if not checked_entry_result["need_update_database"]:
            return res

        if not checked_entry_result["need_download"]:
            return res
        logger.info(f"Syncing to Telegram: {entry['title']}")
        download_info = await sync(
            entry["link"],
            tg_id=self.config["tg_target"] if self.config["tg_target"] else os.environ["DEFAULT_TG_TARGET"],
            sync_audio=not self.config.get("skip_audio", False),
            sync_video=not self.config.get("skip_video", False),
            clean=False,
        )
        res["download_info"] = download_info
        return res

    def update_database(self, checked_info: dict, db_name: str = "metadata") -> None:
        """Update the database with the checked entry information.

        Args:
            checked_info (dict): The checked entry information.
            db_name (str, optional): Database name. Defaults to "metadata".
        """
        if checked_info["need_update_database"]:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self.database.insert(0, checked_info["metadata"])
            save_json(self.database, self.db_path)
            gh.upload_release(self.db_path, db_name)

    def upload_files(self, file_type: str, info_list: list[dict], vid: str) -> list[Path]:
        if len(info_list) == 0:
            return []
        assert file_type in {"audio", "video"}
        upload_files = []
        for idx, info in enumerate(info_list):
            filepath = Path(info[f"{file_type}_path"])
            new_path = filepath.with_stem(f"{vid}-P{idx+1}") if idx > 0 else filepath.with_stem(vid)
            logger.info(f"Upload {filepath.name} to GitHub with new name: {new_path.name}")
            logger.debug(f"Rename {filepath.name} to {new_path.name}")
            filepath.rename(new_path)
            gh.upload_release(new_path.as_posix(), self.name, clean=False)
            upload_files.append(new_path)
        return upload_files

    def get_pod_items(self, pod_type: str, info_list: list[dict], vid: str, entry: dict, cover: str) -> list[dict]:
        if len(info_list) == 0:
            return []
        assert pod_type in {"audio", "video"}
        pod_items = []
        for idx, info in enumerate(info_list):
            original_filepath = Path(info[f"{pod_type}_path"])
            real_path = original_filepath.with_stem(f"{vid}-P{idx+1}") if idx > 0 else original_filepath.with_stem(vid)
            pod_item = generate_pod_item(
                entry,
                pod_type=pod_type,
                release_name=self.name,
                filepath=real_path,
                cover=cover,
                duration=info["duration"],
            )
            real_path.unlink(missing_ok=True)
            pod_items.append(pod_item)
        return pod_items

    def update_pod_rss(self, pod_type: str, pod_items: list[dict], feed: dict) -> None:
        if len(pod_items) == 0:
            return
        assert pod_type in {"audio", "video"}

        Path(pod_type).mkdir(parents=True, exist_ok=True)
        cached_rss = load_xml(f"{pod_type}/{self.name}.xml")
        cached_items = cached_rss["rss"]["channel"].get("item", [])
        if isinstance(cached_items, dict):
            cached_items = [cached_items]
        pod_items.extend(cached_items)
        pod_header = generate_pod_header(feed, self.config)
        save_xml(pod_header, pod_items, f"{pod_type}/{self.name}.xml")
        gh.upload_release(f"{pod_type}/{self.name}.xml", pod_type)
