# X → Discord bridge (Hashtag United)

Dette projekt sender automatisk nye opslag fra Hashtag Uniteds X-konto (`@hashtagutd`) videre til en Discord-kanal via en webhook.

## Krav

- Python 3.10+
- En **X API Bearer Token** (fra X Developer Portal)
- En Discord kanal med en **Incoming Webhook URL**

## Opsætning

1. Installer dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Opret `.env` ud fra `.env.example`:

```bash
cp .env.example .env
```

3. Udfyld i `.env`:

- `X_BEARER_TOKEN`
- `DISCORD_WEBHOOK_URL`
- (valgfrit) `X_USERNAME` hvis du vil tracke en anden konto

## Kør

```bash
python bridge.py
```

## Hvordan den virker

- Botten finder user ID for `X_USERNAME`
- Den poller nye tweets hvert `POLL_INTERVAL_SECONDS`
- Kun originale posts sendes (ingen replies eller retweets)
- Sidste tweet-id gemmes i `state.json`, så samme post ikke sendes to gange

## Deploy forslag

Kør den som en service på en VPS (fx med `systemd`) så den altid er online.

Eksempel `systemd`-service:

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
