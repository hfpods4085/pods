#! /usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

import requests
from loguru import logger


def get_cloud_cookie():
    url = f"{os.environ['COOKIE_CLOUD_SERVER']}/get/{os.environ['COOKIE_CLOUD_KEY']}"
    payload = json.dumps({"password": os.environ["COOKIE_CLOUD_PASS"]})
    headers = {"Content-Type": "application/json"}
    response = requests.request("POST", url, headers=headers, data=payload, timeout=10)
    return json.loads(response.text)


def netscape_format(cookies: list) -> str:
    cookie_str = ""
    for cookie in cookies:
        if args.no_subdomain and cookie["hostOnly"] is True:
            logger.warning(f"Skip cookies of subdomain: {cookie['domain']}")
            continue
        logger.info(f'''Get cookie "{cookie['name']}" of domain "{cookie['domain']}"''')
        subdomains = "FALSE" if cookie["hostOnly"] else "TRUE"
        secure = "TRUE" if cookie["secure"] else "FALSE"
        cookie_str += f"{cookie['domain']}\t{subdomains}\t{cookie['path']}\t{secure}\t{round(cookie.get('expirationDate', 0))}\t{cookie['name']}\t{urllib.parse.quote_plus(cookie['value'])}\n"
    return cookie_str


def main():
    cookie_path = Path(args.cookie_path).expanduser()
    if not cookie_path.exists() or args.force:
        logger.info("Get cookie from cloud server")
        data = get_cloud_cookie()
        cookies: dict = data.get("cookie_data", {})
        matched_domains = [domain for domain in cookies if domain.endswith(args.root_domain)]
        cookie_str = "# Netscape HTTP Cookie File\n"
        cookie_str += "# Domain\tIncludeSubdomains\tPath\tSecure\tExpiry\tName\tValue\n\n"
        cookie_str += "".join([netscape_format(cookies[domain]) for domain in matched_domains])
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        with cookie_path.open("w") as f:
            f.write(cookie_str)
    else:
        logger.info(f"Cookie file already exists at {cookie_path}")


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description="Description of the ArgumentParser")
    parser.add_argument("--log-level", type=str, default="INFO", required=False, help="Log level")
    parser.add_argument("-p", "--cookie-path", type=str, default="cookie.txt", required=False, help="Path of the cookie file")
    parser.add_argument("-d", "--root-domain", type=str, default="bilibili.com", required=False, help="Domain of the cookies")
    parser.add_argument("-s", "--no-subdomain", action="store_true", help="Ignore subdomain cookies")
    parser.add_argument("-f", "--force", action="store_true", help="force update cookie from cloud server")
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
