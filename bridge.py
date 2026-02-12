import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("x-discord-bridge")


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
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.x_bearer_token}",
                "User-Agent": "hashtag-utd-x-discord-bridge/1.0",
            }
        )
        self.user_id: Optional[str] = None

    def _load_last_seen_id(self) -> Optional[str]:
        if not self.config.state_file.exists():
            return None

        try:
            data = json.loads(self.config.state_file.read_text(encoding="utf-8"))
            return data.get("last_seen_id")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Kunne ikke læse state fil: %s", exc)
            return None

    def _save_last_seen_id(self, tweet_id: str) -> None:
        payload = {"last_seen_id": tweet_id}
        self.config.state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _get_user_id(self) -> str:
        if self.user_id:
            return self.user_id

        url = f"https://api.x.com/2/users/by/username/{self.config.x_username}"
        response = self.session.get(url, timeout=20)
        if response.status_code >= 400:
            raise BridgeError(
                f"Kunne ikke hente user id ({response.status_code}): {response.text}"
            )

        payload = response.json()
        user_data = payload.get("data")
        if not user_data or not user_data.get("id"):
            raise BridgeError(f"Ugyldigt svar fra X API: {payload}")

        self.user_id = user_data["id"]
        logger.info("Fundet X user id for @%s", self.config.x_username)
        return self.user_id

    def _fetch_new_tweets(self, since_id: Optional[str]) -> list[dict]:
        user_id = self._get_user_id()
        url = f"https://api.x.com/2/users/{user_id}/tweets"

        params = {
            "max_results": 10,
            "tweet.fields": "created_at,public_metrics",
            "exclude": "retweets,replies",
        }
        if since_id:
            params["since_id"] = since_id

        response = self.session.get(url, params=params, timeout=20)
        if response.status_code >= 400:
            raise BridgeError(
                f"Kunne ikke hente tweets ({response.status_code}): {response.text}"
            )

        payload = response.json()
        tweets = payload.get("data", [])
        tweets.sort(key=lambda t: int(t["id"]))
        return tweets

    def _post_to_discord(self, tweet: dict) -> None:
        tweet_id = tweet["id"]
        tweet_text = tweet.get("text", "")
        tweet_url = f"https://x.com/{self.config.x_username}/status/{tweet_id}"

        embed = {
            "title": f"Ny post fra @{self.config.x_username}",
            "description": tweet_text,
            "url": tweet_url,
            "color": 1942002,
            "footer": {"text": "X → Discord bridge"},
        }

        payload = {
            "username": "Hashtag Utd X Bot",
            "content": f"🚨 Nyt opslag fra @{self.config.x_username}: {tweet_url}",
            "embeds": [embed],
        }

        response = requests.post(self.config.discord_webhook_url, json=payload, timeout=20)
        if response.status_code >= 400:
            raise BridgeError(
                f"Kunne ikke sende til Discord ({response.status_code}): {response.text}"
            )

    def run(self) -> None:
        logger.info("Starter bridge for @%s", self.config.x_username)
        last_seen_id = self._load_last_seen_id()

        if not last_seen_id:
            logger.info(
                "Ingen eksisterende state fundet. Henter seneste tweet som startpunkt."
            )
            tweets = self._fetch_new_tweets(since_id=None)
            if tweets:
                newest = tweets[-1]["id"]
                self._save_last_seen_id(newest)
                last_seen_id = newest
                logger.info(
                    "Initialiseret state med tweet id %s (ingen historiske posts sendt)",
                    newest,
                )

        while True:
            try:
                tweets = self._fetch_new_tweets(since_id=last_seen_id)
                if tweets:
                    for tweet in tweets:
                        self._post_to_discord(tweet)
                        last_seen_id = tweet["id"]
                        self._save_last_seen_id(last_seen_id)
                        logger.info("Sendte tweet %s til Discord", last_seen_id)
                else:
                    logger.debug("Ingen nye tweets")
            except BridgeError as exc:
                logger.error("Bridge fejl: %s", exc)
            except requests.RequestException as exc:
                logger.error("Netværksfejl: %s", exc)

            time.sleep(self.config.poll_interval_seconds)


def load_config() -> Config:
    x_bearer_token = os.getenv("X_BEARER_TOKEN", "").strip()
    x_username = os.getenv("X_USERNAME", "hashtagutd").strip()
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    state_file = Path(os.getenv("STATE_FILE", "state.json"))

    missing = [
        name
        for name, value in [
            ("X_BEARER_TOKEN", x_bearer_token),
            ("DISCORD_WEBHOOK_URL", discord_webhook_url),
        ]
        if not value
    ]

    if missing:
        raise BridgeError(f"Manglende miljøvariabler: {', '.join(missing)}")

    return Config(
        x_bearer_token=x_bearer_token,
        x_username=x_username,
        discord_webhook_url=discord_webhook_url,
        poll_interval_seconds=poll_interval,
        state_file=state_file,
    )


if __name__ == "__main__":
    cfg = load_config()
    bridge = XToDiscordBridge(cfg)
    bridge.run()
