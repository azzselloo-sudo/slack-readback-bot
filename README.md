# slack-readback-bot

A zero-state Slack reminder bot. Drop links and notes into a channel, and the bot
collects the ones you have not dealt with yet and posts them back on a schedule, so
nothing gets buried. No database: it reads the channel itself to decide what is still open.

채널에 "다시 볼 거"(링크·메모)를 던져두면, 봇이 아직 처리 안 한 것만 모아서 정해진 시간에 다시 올려줍니다. DB 없음: 채널 자체를 읽어서 상태를 판단합니다.

## How it works · 동작 방식

You mark each original message:

| You do | Status | Result |
|---|---|---|
| ✅ reaction, or reply `done` / `확인` | resolved | dropped from reminders |
| 💤 reaction, or reply `snooze` / `보류` | snoozed | dropped from daily, shown in the weekly digest |
| nothing | open | shown in the daily digest |

There is no state file. The bot figures everything out by reading the channel each run, and it avoids double-posting by checking its own past messages.

상태는 원본 메시지의 반응/답글로 정해집니다. ✅(또는 답글 '확인')=해결, 💤(또는 답글 '보류')=보류(주간에만), 아무것도 없으면 미확인(매일 뜸). 상태 파일이 없어서 채널만 읽으면 되고, 자기 과거 글을 확인해 중복 발송을 막습니다.

## Setup · 셋업 (3 steps)

> **Easiest path** : open Claude Code in this folder and say `read this kit folder and help me set it up` — it walks you through the steps below.
> **제일 쉬운 방법** : 이 폴더에서 클로드코드를 켜고 `이 키트 폴더 보고 셋업 도와줘` 라고 치세요. 아래 3단계를 클로드가 안내·대행합니다.

**1. Create a Slack app and get a bot token**

At [api.slack.com/apps](https://api.slack.com/apps), create an app, add these Bot Token Scopes under OAuth & Permissions, install to your workspace, and copy the `xoxb-...` token:

`channels:history`, `channels:read`, `chat:write`, `reactions:read` (add `groups:history` for private channels)

Invite the bot to your channel: `/invite @your-bot`

**2. Configure (one command)**

```bash
pip install -r requirements.txt
python readback.py setup              # checks the token, lists your channels, writes .env + config.json
```

The wizard verifies your token, shows the channels the bot is in so you just pick a number, and writes both files for you. No hand-editing JSON.

셋업 마법사가 토큰을 확인하고, 봇이 들어간 채널을 목록으로 보여줘서 번호만 고르면 `.env`와 `config.json`을 자동으로 만들어줍니다. JSON 직접 편집 불필요.

Prefer to do it by hand? Copy `.env.example` -> `.env` (paste your `xoxb-` token) and `config.example.json` -> `config.json` (add your channel IDs). Find a channel ID in Slack: channel name -> View channel details -> bottom of the popup.

**3. Run**

```bash
python readback.py daily --dry        # preview, posts nothing
python readback.py daily              # post the open-items digest
python readback.py weekly             # post the snoozed-items digest
python readback.py loop               # resident mode: posts at configured local slots
```

## Deploy free with GitHub Actions · 깃헙 액션으로 무료 구동

No server needed. The included `.github/workflows/reminder.yml` runs the reminder on a cron.

서버 필요 없음. 포함된 워크플로우가 cron으로 자동 실행합니다.

1. Repo Settings -> Secrets and variables -> Actions
   - **Secret** `SLACK_BOT_TOKEN` = your `xoxb-...` token
   - **Variable** `READBACK_CONFIG` = the full contents of your `config.json`
     (config.json is gitignored, so it is supplied as a variable)
2. The workflow fires the daily digest at 13:00 and 22:00 KST and the weekly digest Monday 13:00 KST. Edit the `cron` lines for your timezone (cron is in UTC).

## Config · 설정 (`config.json`)

| key | meaning |
|---|---|
| `channels` | channel IDs to read and post into (required) |
| `owner` | only remind this user's messages; `""` = everyone |
| `lookback_days` | how far back the daily digest looks |
| `weekly_lookback_days` | how far back the weekly digest looks |
| `timezone_offset_hours` | local time for slots and dedupe (9 = KST) |
| `daily_hours` | local hours the `loop` mode posts the daily digest |
| `weekly_day` / `weekly_hour` | 0=Mon .. 6=Sun, and the hour, for the weekly digest |
| `resolve_reactions` / `snooze_reactions` | reaction names that mark resolved / snoozed |
| `resolve_keywords` / `snooze_keywords` | reply words that mark resolved / snoozed |

## Test · 테스트

```bash
python test_readback.py
```

Tests cover the pure logic (status decision, message chunking) with no Slack calls.

## License

MIT
