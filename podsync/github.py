#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import requests
from loguru import logger

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "X-GitHub-Api-Version": "2022-11-28",
}


class Github:
    def __init__(self, repo: str = os.getenv("GITHUB_REPOSITORY", "")) -> None:
        self.repo = repo
        assert self.repo, "Repo is not set"
        self.releases = {}

    def get_releases(self) -> dict[str, dict]:
        logger.debug(f"Fetching releases of {self.repo}")
        if self.releases:
            return self.releases
        all_releases = []
        per_page = 100  # maximum is 100
        page = 1
        res = requests.get(f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=HEADERS, timeout=30).json()
        all_releases.extend(res)
        while len(res) == per_page:
            page += 1
            res = requests.get(f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=HEADERS, timeout=30).json()
            all_releases.extend(res)
        logger.debug(f"Found {len(all_releases)} releases")
        self.releases = {release["name"]: release for release in all_releases}
        return self.releases

    def get_release_assets(self, name: str) -> dict[str, dict]:
        logger.debug(f"Getting release assets of {self.repo}, release name: {name}")
        if not self.releases:
            release = self.get_releases().get(name, {})
        release = self.get_releases().get(name, {})
        return {
            asset["name"]: {
                "updated_at": asset["updated_at"],
                "id": asset["id"],
            }
            for asset in release.get("assets", [])
        }

    def delete_release(self, release_name: str):
        logger.debug(f"Delete {release_name} [{self.repo}]")
        command = f"gh release delete '{release_name}' --cleanup-tag --yes"
        subprocess.run(command, shell=True, check=False)  # noqa: S602

    def delete_asset(self, asset_id: int):
        logger.debug(f"Delete asset {asset_id} [{self.repo}]")
        requests.delete(f"https://api.github.com/repos/{self.repo}/releases/assets/{asset_id}", headers=HEADERS, timeout=30)

    def edit_release(self, release_name: str, body: str, *, prerelease: bool = False, latest: bool = False, draft: bool = False):
        logger.debug(f"Edit release {release_name} [{self.repo}]")
        release = self.get_releases().get(release_name, {})
        if "id" not in release:
            return
        api = f"https://api.github.com/repos/{self.repo}/releases/{release['id']}"
        data = {"tag_name": release_name, "body": body, "prerelease": prerelease, "make_latest": latest, "draft": draft}
        requests.patch(api, headers=HEADERS, json=data, timeout=30)

    def upload_release(self, path: str | Path, release_name: str, *, clean=False):
        path = Path(path).resolve()
        assert path.exists(), f"File not found: {path}"
        if not self.releases:
            self.releases = self.get_releases()
        if release_name not in self.releases:
            logger.info(f"Creating release {release_name} [{self.repo}]")
            command = f"gh release create '{release_name}' --prerelease -n '{release_name}' -t '{release_name}' -R '{self.repo}' > /dev/null 2>&1 || true"
            subprocess.run(command, shell=True, check=False)  # noqa: S602
        logger.info(f"Uploading {path.name} to {release_name} [{self.repo}]")
        command = f"gh release upload --clobber '{release_name}' -- '{path.as_posix()}'"
        subprocess.run(command, shell=True, check=False)  # noqa: S602
        if clean:
            path.unlink(missing_ok=True)

    def trigger_workflow(self, feed_name: str, platform: str = "youtube") -> int:
        logger.info(f"Triggering workflow for {feed_name}")
        api = f"https://api.github.com/repos/{self.repo}/actions/workflows/single.yml/dispatches"
        data = {"ref": "main", "inputs": {"name": feed_name, "platform": platform}}
        response = requests.post(api, headers=HEADERS, json=data, timeout=30)
        assert response.status_code == 204, f"Failed to trigger workflow: {response.text}"
        return response.status_code


gh = Github()
