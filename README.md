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

## GitHub Actions manual test (Run workflow)

You can manually test the integration from GitHub without running the bot continuously.

1. In your repository, go to **Settings → Secrets and variables → Actions** and add credentials as either **Secrets** (recommended) or **Variables**:
   - `DISCORD_WEBHOOK_URL`
   - one of: `X_BEARER_TOKEN`, `X_API_BEARER_TOKEN`, or `TWITTER_BEARER_TOKEN`
2. Go to **Actions** and open the workflow **Manual X -> Discord test**.
3. Click **Run workflow**.
4. (Optional) Set `x_username` (without `@`) if you want to test another account.
5. The workflow runs `python bridge.py --send-latest-once`, which fetches the latest original post and sends it to your Discord channel once.

This is intended for manual validation and does not use `state.json`.

If the workflow fails with a missing bearer token, verify the name exactly matches one of the supported names above and that the value is set on the repository/environment where the workflow runs.

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
