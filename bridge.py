import argparse
import html
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# Load environment variables from .env before creating config/logging objects.
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("x-discord-bridge")

DEFAULT_PUBLIC_X_RSS_URL_TEMPLATES = [
    "https://nitter.net/{username}/rss",
    "https://nitter.poast.org/{username}/rss",
    "https://nitter.privacydev.net/{username}/rss",
]


@dataclass
class Config:
    x_bearer_token: str
    x_username: str
    discord_webhook_url: str
    poll_interval_seconds: int
    state_file: Path


class BridgeError(Exception):
    pass


class XToDiscordBridge:
    def __init__(self, config: Config) -> None:
        self.config = config

        # Keep one reusable HTTP session for all X API requests.
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.x_bearer_token}",
                "User-Agent": "hashtag-utd-x-discord-bridge/1.0",
            }
        )
        self.user_id: Optional[str] = None

    def _load_last_seen_id(self) -> Optional[str]:
        # If the state file does not exist yet, this is the first run.
        if not self.config.state_file.exists():
            return None

        try:
            data = json.loads(self.config.state_file.read_text(encoding="utf-8"))
            return data.get("last_seen_id")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read state file: %s", exc)
            return None

    def _save_last_seen_id(self, tweet_id: str) -> None:
        payload = {"last_seen_id": tweet_id}
        self.config.state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _get_user_id(self) -> str:
        # Cache the user id after first lookup to avoid repeating this request.
        if self.user_id:
            return self.user_id

        url = f"https://api.x.com/2/users/by/username/{self.config.x_username}"
        response = self.session.get(url, timeout=20)
        if response.status_code >= 400:
            raise BridgeError(
                f"Could not fetch user id ({response.status_code}): {response.text}"
            )

        payload = response.json()
        user_data = payload.get("data")
        if not user_data or not user_data.get("id"):
            raise BridgeError(f"Invalid response from X API: {payload}")

        self.user_id = user_data["id"]
        logger.info("Found X user id for @%s", self.config.x_username)
        return self.user_id

    def _fetch_new_tweets(self, since_id: Optional[str]) -> list[dict]:
        user_id = self._get_user_id()
        url = f"https://api.x.com/2/users/{user_id}/tweets"

        # Request original tweets only and keep the payload lightweight.
        params = {
            "max_results": 10,
            "tweet.fields": "created_at,public_metrics",
            "exclude": "retweets,replies",
        }
        if since_id:
            # Ask only for tweets newer than the latest processed tweet id.
            params["since_id"] = since_id

        response = self.session.get(url, params=params, timeout=20)
        if response.status_code >= 400:
            raise BridgeError(
                f"Could not fetch tweets ({response.status_code}): {response.text}"
            )

        payload = response.json()
        tweets = payload.get("data", [])

        # Sort oldest -> newest so Discord receives posts in the right order.
        tweets.sort(key=lambda t: int(t["id"]))
        return tweets

    def _fetch_latest_tweet(self) -> Optional[dict]:
        """Fetch the latest original tweet (excluding replies/retweets)."""
        tweets = self._fetch_new_tweets(since_id=None)
        if not tweets:
            return None
        return tweets[-1]

    def _post_to_discord(self, tweet: dict) -> None:
        tweet_id = tweet["id"]
        tweet_text = tweet.get("text", "")
        tweet_url = f"https://x.com/{self.config.x_username}/status/{tweet_id}"

        embed = {
            "title": f"New post from @{self.config.x_username}",
            "description": tweet_text,
            "url": tweet_url,
            "color": 1942002,
            "footer": {"text": "X → Discord bridge"},
        }

        payload = {
            "username": "Hashtag Utd X Bot",
            "content": f"🚨 New post from @{self.config.x_username}: {tweet_url}",
            "embeds": [embed],
        }

        response = requests.post(self.config.discord_webhook_url, json=payload, timeout=20)
        if response.status_code >= 400:
            raise BridgeError(
                f"Could not send to Discord ({response.status_code}): {response.text}"
            )

    def run(self) -> None:
        logger.info("Starting bridge for @%s", self.config.x_username)
        last_seen_id = self._load_last_seen_id()

        if not last_seen_id:
            logger.info(
                "No existing state found. Fetching latest tweet as starting point."
            )
            tweets = self._fetch_new_tweets(since_id=None)
            if tweets:
                # Initialize state with current latest tweet to avoid backfilling old posts.
                newest = tweets[-1]["id"]
                self._save_last_seen_id(newest)
                last_seen_id = newest
                logger.info(
                    "Initialized state with tweet id %s (historical posts were not sent)",
                    newest,
                )

        while True:
            try:
                tweets = self._fetch_new_tweets(since_id=last_seen_id)
                if tweets:
                    for tweet in tweets:
                        # Forward each new tweet and persist progress immediately.
                        self._post_to_discord(tweet)
                        last_seen_id = tweet["id"]
                        self._save_last_seen_id(last_seen_id)
                        logger.info("Sent tweet %s to Discord", last_seen_id)
                else:
                    logger.debug("No new tweets")
            except BridgeError as exc:
                logger.error("Bridge error: %s", exc)
            except requests.RequestException as exc:
                logger.error("Network error: %s", exc)

            # Sleep between poll cycles to respect API limits and reduce noise.
            time.sleep(self.config.poll_interval_seconds)

    def send_latest_tweet_once(self) -> None:
        """One-shot mode used for manual validation (official X API mode)."""
        logger.info("Running one-shot test: fetch latest tweet via X API and post to Discord")
        tweet = self._fetch_latest_tweet()
        if not tweet:
            logger.info("No tweets found for @%s", self.config.x_username)
            return

        self._post_to_discord(tweet)
        logger.info("Successfully sent latest tweet %s to Discord", tweet["id"])


def send_webhook_test_message(webhook_url: str, x_username: str) -> None:
    """Send a Discord-only test message that does not require an X API token."""
    payload = {
        "username": "Hashtag Utd X Bot",
        "content": (
            "✅ Webhook-only test succeeded. "
            f"This message confirms Discord webhook delivery for @{x_username}."
        ),
    }
    response = requests.post(webhook_url, json=payload, timeout=20)
    if response.status_code >= 400:
        raise BridgeError(
            f"Could not send webhook-only test message ({response.status_code}): {response.text}"
        )


def _get_public_rss_templates() -> list[str]:
    """Resolve RSS templates from env or use built-in defaults."""
    templates_csv = os.getenv("PUBLIC_X_RSS_URL_TEMPLATES", "").strip()
    if templates_csv:
        templates = [t.strip() for t in templates_csv.split(",") if t.strip()]
        if templates:
            return templates

    single_template = os.getenv("PUBLIC_X_RSS_URL_TEMPLATE", "").strip()
    if single_template:
        return [single_template]

    return DEFAULT_PUBLIC_X_RSS_URL_TEMPLATES


def _extract_latest_rss_item(xml_text: str) -> tuple[str, str, str]:
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        raise BridgeError("RSS feed did not contain a channel node")

    item = channel.find("item")
    if item is None:
        raise BridgeError("RSS feed had no items")

    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    description = (item.findtext("description") or "").strip()
    return title, link, description


def send_latest_public_post_once(config: Config) -> None:
    """Best-effort no-token fallback from public RSS mirrors."""
    templates = _get_public_rss_templates()
    errors: list[str] = []

    for template in templates:
        rss_url = template.format(username=config.x_username)
        logger.info("Fetching latest public RSS item from %s", rss_url)

        try:
            response = requests.get(
                rss_url,
                timeout=20,
                headers={"User-Agent": "hashtag-utd-x-discord-bridge/1.0"},
            )
        except requests.RequestException as exc:
            errors.append(f"{rss_url}: request failed ({exc})")
            continue

        if response.status_code == 429:
            errors.append(f"{rss_url}: rate limited (429)")
            continue

        if response.status_code >= 400:
            errors.append(
                f"{rss_url}: HTTP {response.status_code} {response.text[:120]}"
            )
            continue

        try:
            title, link, description = _extract_latest_rss_item(response.text)
        except (ET.ParseError, BridgeError) as exc:
            errors.append(f"{rss_url}: invalid RSS ({exc})")
            continue

        message_text = html.unescape(title or description or "Latest public post")
        if len(message_text) > 4000:
            message_text = f"{message_text[:3997]}..."

        embed = {
            "title": f"Latest public post from @{config.x_username}",
            "description": message_text,
            "url": link if link else f"https://x.com/{config.x_username}",
            "color": 1942002,
            "footer": {"text": f"X → Discord bridge (public RSS fallback: {rss_url})"},
        }

        payload = {
            "username": "Hashtag Utd X Bot",
            "content": f"📡 Public fallback latest post for @{config.x_username}",
            "embeds": [embed],
        }

        discord_response = requests.post(
            config.discord_webhook_url, json=payload, timeout=20
        )
        if discord_response.status_code >= 400:
            raise BridgeError(
                "Could not send public fallback post to Discord "
                f"({discord_response.status_code}): {discord_response.text}"
            )

        logger.info("Successfully sent latest public fallback post to Discord")
        return

    raise BridgeError(
        "Could not fetch public RSS feed from any mirror. Tried: " + " | ".join(errors)
    )


def load_config(require_x_token: bool = True) -> Config:
    x_bearer_token = (
        os.getenv("X_BEARER_TOKEN", "").strip()
        or os.getenv("X_API_BEARER_TOKEN", "").strip()
        or os.getenv("TWITTER_BEARER_TOKEN", "").strip()
    )
    x_username = os.getenv("X_USERNAME", "hashtagutd").strip()
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    state_file = Path(os.getenv("STATE_FILE", "state.json"))

    # Validate required settings before starting the bridge loop.
    missing = []
    if require_x_token and not x_bearer_token:
        missing.append("X_BEARER_TOKEN (or X_API_BEARER_TOKEN / TWITTER_BEARER_TOKEN)")
    if not discord_webhook_url:
        missing.append("DISCORD_WEBHOOK_URL")

    if missing:
        raise BridgeError(f"Missing environment variables: {', '.join(missing)}")

    return Config(
        x_bearer_token=x_bearer_token,
        x_username=x_username,
        discord_webhook_url=discord_webhook_url,
        poll_interval_seconds=poll_interval,
        state_file=state_file,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forward posts from X to Discord.")
    parser.add_argument(
        "--send-latest-once",
        action="store_true",
        help=(
            "Fetch the latest post from X API and send it to Discord once, then exit. "
            "Requires X token."
        ),
    )
    parser.add_argument(
        "--send-latest-public-once",
        action="store_true",
        help=(
            "Fetch latest post from a public RSS mirror and send it once to Discord. "
            "No X token required."
        ),
    )
    parser.add_argument(
        "--webhook-test-only",
        action="store_true",
        help=(
            "Send a Discord webhook-only test message and exit. "
            "Does not fetch from X and does not require an X token."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.webhook_test_only:
        cfg = load_config(require_x_token=False)
        send_webhook_test_message(cfg.discord_webhook_url, cfg.x_username)
    elif args.send_latest_public_once:
        cfg = load_config(require_x_token=False)
        send_latest_public_post_once(cfg)
    else:
        cfg = load_config(require_x_token=True)
        bridge = XToDiscordBridge(cfg)
        if args.send_latest_once:
            bridge.send_latest_tweet_once()
        else:
            bridge.run()
