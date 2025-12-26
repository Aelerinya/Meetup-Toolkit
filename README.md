# Meetup-Toolkit

Tools manage my meetups, especially syncing event between platforms

## Setup

1. Copy `.env.example` to `.env`
2. Add your LessWrong loginToken (see `.env.example` for instructions)
3. Edit `config.toml` to customize location and group settings

## Partiful to LessWrong: `sync_event.py`

Sync events from Partiful to LessWrong. Automatically creates or updates LessWrong events with details from Partiful.

### Usage

```bash
uv run sync_event.py https://partiful.com/e/EVENT_ID
```

## Ressources
https://www.lesswrong.com/posts/LJiGhpq8w4Badr5KJ/graphql-tutorial-for-lesswrong-and-effective-altruism-forum