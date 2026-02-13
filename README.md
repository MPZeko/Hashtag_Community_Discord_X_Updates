# X → Discord bridge (Hashtag United)

This project automatically forwards new posts from Hashtag United's X account (`@hashtagutd`) to a Discord channel via a webhook.

## Requirements

- Python 3.10+
- An **X API Bearer Token** (from the X Developer Portal)
- A Discord channel with an **Incoming Webhook URL**

## Setup

1. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

3. Fill out the values in `.env`:

- `X_BEARER_TOKEN`
- `DISCORD_WEBHOOK_URL`
- (optional) `X_USERNAME` if you want to track another account
- (optional) `POLL_INTERVAL_SECONDS` (defaults to `60`)
- (optional) `STATE_FILE` (defaults to `state.json`)

## Run

```bash
python bridge.py
```

## How it works

- The bridge posts to Discord using the `DISCORD_WEBHOOK_URL` webhook endpoint.
- The bot looks up the user ID for `X_USERNAME`.
- It polls for new tweets every `POLL_INTERVAL_SECONDS`.
- Only original posts are forwarded (no replies or retweets).
- The last processed tweet ID is stored in `state.json`, so the same post is not sent twice.

## Testing / validation

This repository currently does not include automated unit tests, but you can still validate the setup with these checks:

```bash
python -m py_compile bridge.py
python -m pip check
```

You can also run a quick live validation:

1. Start the bridge: `python bridge.py`
2. Publish a new post from the tracked X account.
3. Confirm that the post appears in your Discord channel.
4. Restart the bridge and verify the same post is not re-sent.

## GitHub Actions (manual + automatic schedule)

You can run the integration from GitHub Actions both manually and automatically on a schedule.

1. In your repository, go to **Settings → Secrets and variables → Actions** and add credentials as either **Secrets** (recommended) or **Variables**:
   - `DISCORD_WEBHOOK_URL` (always required)
   - one of: `X_BEARER_TOKEN`, `X_API_BEARER_TOKEN`, or `TWITTER_BEARER_TOKEN` (required only for `latest_post` mode)
2. (Optional for automatic runs) Add these Actions Variables:
   - `AUTO_TEST_MODE` (default: `latest_public_no_token`)
   - `AUTO_X_USERNAME` (default: `hashtagutd`)
3. The workflow runs automatically every 5 minutes (`cron: */5 * * * *`).
4. For manual testing, go to **Actions** and open **Manual X -> Discord test**, then click **Run workflow**.
5. Choose `test_mode` (manual run):
   - `latest_post`: fetch latest post from official X API and send it to Discord (**requires token**).
   - `latest_public_no_token`: fetch latest post from public RSS mirrors and send it to Discord (**no token**, best-effort).
   - `webhook_only`: send a Discord test message only (**no token**, does not fetch from X).
6. (Optional) Set `x_username` (without `@`) if you want to test another account.
7. (Optional) Add `PUBLIC_X_RSS_URL_TEMPLATES` (comma-separated) as an Actions Variable to override fallback RSS mirrors.
   - Example: `https://nitter.net/{username}/rss,https://nitter.poast.org/{username}/rss`
   - Backward-compatible single-source variable: `PUBLIC_X_RSS_URL_TEMPLATE`

This is intended for manual validation and does not use `state.json`.

If you do not have an X token, use `latest_public_no_token` or `webhook_only`.

Note: GitHub Actions is polling-based, not real-time streaming. With `*/5` schedule, new posts are usually picked up within a few minutes.

## Deployment suggestion

Run it as a service on a VPS (for example with `systemd`) so it stays online.

Example `systemd` service:

```ini
[Unit]
Description=Hashtag United X to Discord Bridge
After=network.target

[Service]
WorkingDirectory=/path/to/Hashtag_Community_Discord_X_Updates
ExecStart=/path/to/.venv/bin/python bridge.py
Restart=always
RestartSec=5
EnvironmentFile=/path/to/Hashtag_Community_Discord_X_Updates/.env

[Install]
WantedBy=multi-user.target
```
