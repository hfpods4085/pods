#! /usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import json
from pathlib import Path

from github import gh


def load_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def delete_old_assets(assets: dict[str, dict], keep: int = 40):
    sorted_assets = sorted(assets.items(), key=lambda x: x[1]["updated_at"], reverse=True)
    for name, asset in sorted_assets[keep:]:
        if Path(name).suffix in {".mp4", ".m4a", ".mp3"}:
            print(f"Delete {name}")
            gh.delete_asset(asset["id"])


def main():
    for conf_path in Path(args.config_dir).glob("*.json"):
        configs = load_json(conf_path)
        for conf in configs:
            print(f"Processing {conf['name']}")
            keep = args.keep // 2 if conf.get("skip_audio") or conf.get("skip_video") else args.keep
            assets = gh.get_release_assets(conf["name"])
            delete_old_assets(assets, keep)


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Sync YouTube to Telegram")
    parser.add_argument("--config-dir", type=str, default="config", required=False, help="Configuration directory")
    parser.add_argument("--keep", type=int, default=40, required=False, help="How many assets to keep")
    args = parser.parse_args()
    main()
