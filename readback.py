"""
slack-readback-bot

A zero-state Slack reminder bot. It collects the "look at this again" items
(links and notes) someone dropped in a channel and posts them back on a schedule
so they do not get buried. There is no database: the bot reads the channel itself
to decide what is still open.

Status is driven by reactions / replies on the ORIGINAL message:
  - resolved : a check reaction, or a reply containing a resolve keyword  -> dropped from reminders
  - snoozed  : a snooze reaction, or a reply containing a snooze keyword   -> dropped from daily, shown in the weekly digest
  - open     : neither -> shown in the daily digest

Run modes:
  python readback.py setup     # one-time wizard: check the token, pick channels, write .env + config.json
  python readback.py daily     # post the open-items digest now (let cron/Actions pick the time)
  python readback.py weekly    # post the snoozed-items digest (run once a week)
  python readback.py loop      # resident mode: watch the clock and post at configured KST-style slots
  python readback.py daily --dry   # print, do not post (works on any mode)

Env: SLACK_BOT_TOKEN (xoxb-...). Scopes: channels:history, channels:read,
chat:write, reactions:read (+ groups:history for private channels).
"""
import os
import re
import sys
import json
import time
import html
import urllib.request
from pathlib import Path

from slack_sdk import WebClient

HERE = Path(__file__).parent

# .env auto-load for local runs (on CI / hosts use real env vars)
_envf = HERE / ".env"
if _envf.exists():
    for _line in _envf.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())


def load_config():
    """config.json overrides the defaults below. Only channels is required."""
    defaults = {
        "channels": [],                 # channel IDs to read + post into
        "owner": "",                    # only remind this user's messages; "" = everyone
        "lookback_days": 14,            # how far back the daily digest looks
        "weekly_lookback_days": 60,     # how far back the weekly (snoozed) digest looks
        "timezone_offset_hours": 9,     # local time used for slots and dedupe (9 = KST)
        "daily_hours": [13, 22],        # hours (local) the loop posts the daily digest
        "weekly_day": 0,                # 0=Mon .. 6=Sun (local)
        "weekly_hour": 13,
        "resolve_reactions": ["white_check_mark", "heavy_check_mark", "ballot_box_with_check"],
        "snooze_reactions": ["zzz", "alarm_clock", "bookmark"],
        "resolve_keywords": ["확인", "완료", "done", "끝", "read", "checked"],
        "snooze_keywords": ["보류", "나중에", "later", "snooze", "pass"],
        "daily_marker": "Readback reminder",
        "weekly_marker": "Snoozed readback",
    }
    path = HERE / "config.json"
    if path.exists():
        defaults.update(json.loads(path.read_text(encoding="utf-8")))
    return defaults


CFG = load_config()


# ---------- time ----------
def _now_local(cfg=CFG):
    """struct_time in the configured local zone (offset-based, no DST)."""
    return time.gmtime(time.time() + cfg["timezone_offset_hours"] * 3600)


# ---------- link summary ----------
def fetch_link_summary(url):
    """One-line summary of a link (og:description -> og:title -> <title>)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        page = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
        for pat in (r'property="og:description" content="([^"]+)"',
                    r'property="og:title" content="([^"]+)"',
                    r'<title[^>]*>([^<]+)</title>'):
            m = re.search(pat, page)
            if m:
                return " ".join(html.unescape(m.group(1)).split())
    except Exception:
        pass
    return ""


# ---------- status from reactions / replies ----------
def _status_from_reactions_and_replies(reaction_names, reply_texts, cfg=CFG):
    """Pure status decision. resolved beats snoozed.

    reaction_names : iterable of reaction short names on the original message
    reply_texts    : iterable of reply body strings (parent excluded)
    """
    names = set(reaction_names)
    resolve_rx = re.compile("|".join(re.escape(k) for k in cfg["resolve_keywords"]), re.I)
    snooze_rx = re.compile("|".join(re.escape(k) for k in cfg["snooze_keywords"]), re.I)
    if names & set(cfg["resolve_reactions"]):
        return "resolved"
    snoozed = bool(names & set(cfg["snooze_reactions"]))
    for t in reply_texts:
        if resolve_rx.search(t or ""):
            return "resolved"          # a resolve reply wins over snooze
        if snooze_rx.search(t or ""):
            snoozed = True
    return "snoozed" if snoozed else "open"


def _msg_status(client, ch, m, cfg=CFG):
    """Look up a message's status, fetching its replies only when needed."""
    names = [r.get("name") for r in m.get("reactions", [])]
    reply_texts = []
    if m.get("reply_count", 0) > 0:
        try:
            rep = client.conversations_replies(channel=ch, ts=m["ts"], limit=50)
            for r in rep.get("messages", []):
                if r.get("ts") != m.get("ts"):   # skip the parent, replies only
                    reply_texts.append(r.get("text") or "")
        except Exception:
            pass
    return _status_from_reactions_and_replies(names, reply_texts, cfg)


# ---------- message chunking (Slack length cap) ----------
def _chunk_text(text, limit=3800):
    """Split text on line boundaries so nothing is dropped past Slack's limit."""
    chunks, cur = [], ""
    for ln in text.split("\n"):
        if cur and len(cur) + len(ln) + 1 > limit:
            chunks.append(cur)
            cur = ln
        else:
            cur = (cur + "\n" + ln) if cur else ln
    if cur:
        chunks.append(cur)
    return chunks


# ---------- stateless dedupe (read the bot's own past posts) ----------
def _posted_today_at(client, ch, hour, marker, cfg=CFG):
    """True if the bot already posted this marker today at this local hour."""
    today = time.strftime("%Y-%m-%d", _now_local(cfg))
    try:
        resp = client.conversations_history(channel=ch, limit=30)
    except Exception:
        return False
    off = cfg["timezone_offset_hours"] * 3600
    for m in resp.get("messages", []):
        if m.get("bot_id") and marker in (m.get("text") or ""):
            k = time.gmtime(float(m["ts"]) + off)
            if time.strftime("%Y-%m-%d", k) == today and k.tm_hour == hour:
                return True
    return False


def _posted_this_week(client, ch, marker):
    """True if the weekly marker was posted within the last 6 days."""
    cut = time.time() - 6 * 86400
    try:
        resp = client.conversations_history(channel=ch, limit=50)
    except Exception:
        return False
    for m in resp.get("messages", []):
        if m.get("bot_id") and marker in (m.get("text") or "") and float(m.get("ts", 0)) >= cut:
            return True
    return False


# ---------- collect + render ----------
def _collect_items(client, ch, want, cutoff, cfg=CFG):
    """Return original messages in the window whose status == want (newest first)."""
    msgs, cursor = [], None
    for _pg in range(8):                       # up to 1600 messages
        resp = client.conversations_history(channel=ch, limit=200, cursor=cursor)
        msgs.extend(resp.get("messages", []))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not resp.get("has_more") or not cursor:
            break
    owner = cfg.get("owner", "")
    items = []
    for m in msgs:
        if float(m.get("ts", 0)) < cutoff:
            continue
        if m.get("bot_id") or m.get("subtype"):
            continue
        if owner and m.get("user") != owner:
            continue
        if m.get("thread_ts") and m.get("thread_ts") != m.get("ts"):
            continue                            # replies are not items
        if not (m.get("text") or "").strip():
            continue
        if _msg_status(client, ch, m, cfg) != want:
            continue
        items.append(m)
    return items


def _render_digest(client, ch, items, head, cfg=CFG):
    """Build the digest text: every item on its own line, link summary + permalink."""
    lines = [head, ""]
    for m in items:
        txt = (m.get("text") or "").strip()
        d = time.strftime("%m/%d", time.localtime(float(m["ts"])))
        urls = [html.unescape(u) for u in re.findall(r"https?://[^\s|>]+", txt)]
        try:
            pl = client.chat_getPermalink(channel=ch, message_ts=m["ts"]).get("permalink")
        except Exception:
            pl = None
        jump = (f"  ·  <{pl}|open>" if pl else "")
        if urls:
            summ = fetch_link_summary(urls[0]) or "link"
            lines.append(f"• <{urls[0]}|{d} · {summ[:110]}>" + jump)
        else:
            body = " ".join(txt.split())[:140]
            lines.append(f"• {d} · 💭 {body}" + jump)
    return "\n".join(lines)


def run_reminder(client, dry=False, slot_hour=None, weekly=False, cfg=CFG):
    """weekly=False posts open items; weekly=True posts snoozed items."""
    owner = cfg.get("owner", "")
    if weekly:
        cutoff = time.time() - cfg["weekly_lookback_days"] * 86400
        marker, want = cfg["weekly_marker"], "snoozed"
    else:
        cutoff = time.time() - cfg["lookback_days"] * 86400
        marker, want = cfg["daily_marker"], "open"

    for ch in cfg.get("channels", []):
        if not dry:
            if weekly and _posted_this_week(client, ch, marker):
                print(f"[{ch}] weekly digest already sent this week", flush=True)
                continue
            if not weekly and slot_hour is not None and _posted_today_at(client, ch, slot_hour, marker, cfg):
                print(f"[{ch}] daily digest already sent at slot {slot_hour}", flush=True)
                continue

        items = _collect_items(client, ch, want, cutoff, cfg)
        total = len(items)
        if total == 0:
            print(f"[{ch}] no {'snoozed' if weekly else 'open'} items", flush=True)
            continue

        who = f"<@{owner}> " if owner else ""
        if weekly:
            head = (f"🔖 {marker} (weekly) · {who}{total} snoozed\n"
                    "Done? add ✅ on the original. Still later? leave it (it returns next week).")
        else:
            head = (f"📌 {marker} · {who}{total} not seen yet\n"
                    "Seen it: ✅ (or reply 'done'). Later: 💤 (or reply 'snooze').")

        out = _render_digest(client, ch, items, head, cfg)
        if dry:
            print("\n----- digest (not posted) -----\n" + out + "\n-------------------------------\n", flush=True)
        else:
            for chunk in _chunk_text(out):
                client.chat_postMessage(channel=ch, text=chunk, unfurl_links=False, unfurl_media=False)
        print(f"[{ch}] {total} {'snoozed ' if weekly else ''}reminded{' / DRY' if dry else ''}", flush=True)


def loop(client, cfg=CFG):
    """Resident mode: post at configured local slots, sleep between checks."""
    print("readback loop started "
          f"(daily {cfg['daily_hours']}, weekly day {cfg['weekly_day']} @ {cfg['weekly_hour']})", flush=True)
    while True:
        try:
            k = _now_local(cfg)
            if cfg.get("channels"):
                if k.tm_hour in cfg["daily_hours"]:
                    run_reminder(client, slot_hour=k.tm_hour, cfg=cfg)
                if k.tm_wday == cfg["weekly_day"] and k.tm_hour == cfg["weekly_hour"]:
                    run_reminder(client, weekly=True, cfg=cfg)
        except Exception as e:
            print("[loop err]", str(e)[:120], flush=True)
        time.sleep(900)


def setup():
    """One-time wizard: verify the token, pick channels, write .env + config.json.

    Nothing here is posted to Slack. It only reads (auth check + channel list)
    and writes the two local files the bot needs, so a newcomer never has to
    hand-edit JSON.
    """
    print("slack-readback-bot setup\n")

    # 1) token: reuse env/.env if present, else ask and save it
    token = os.environ.get("SLACK_BOT_TOKEN")
    if token:
        print(f"Using SLACK_BOT_TOKEN already in your env/.env ({token[:10]}...).")
    else:
        token = input("Paste your Slack bot token (starts with xoxb-): ").strip()
    if not token:
        sys.exit("No token given. Get one at api.slack.com/apps, then rerun `python readback.py setup`.")

    client = WebClient(token=token)
    try:
        who = client.auth_test()
        print(f"Connected as '{who['user']}' in workspace '{who['team']}'.\n")
    except Exception as e:
        sys.exit(f"Token check failed: {str(e)[:120]}\nFix the token and rerun `python readback.py setup`.")

    envf = HERE / ".env"
    if not envf.exists():
        envf.write_text(f"SLACK_BOT_TOKEN={token}\n", encoding="utf-8")
        print("Saved .env")

    # 2) channels: list the ones the bot is already in, let them pick or paste IDs
    chans = []
    try:
        resp = client.users_conversations(types="public_channel,private_channel", limit=200)
        chans = resp.get("channels", [])
    except Exception:
        pass
    chosen = []
    if chans:
        print("Channels your bot is in:")
        for i, c in enumerate(chans, 1):
            print(f"  {i}. #{c.get('name')}  ({c['id']})")
        pick = input("Pick number(s), comma-separated (or paste channel IDs): ").strip()
        for tok in pick.split(","):
            tok = tok.strip()
            if tok.isdigit() and 1 <= int(tok) <= len(chans):
                chosen.append(chans[int(tok) - 1]["id"])
            elif tok:
                chosen.append(tok)
    else:
        print("Could not list channels. Invite the bot first: /invite @your-bot")
        chosen = [t.strip() for t in input("Channel ID(s), comma-separated: ").split(",") if t.strip()]
    if not chosen:
        sys.exit("No channel chosen. Rerun `python readback.py setup`.")

    # 3) write config.json off the example so all the sensible defaults come along
    example = HERE / "config.example.json"
    cfg = json.loads(example.read_text(encoding="utf-8")) if example.exists() else {}
    cfg["channels"] = chosen
    owner = input("Remind only ONE person's messages? Paste their user ID (U...), or Enter for everyone: ").strip()
    cfg["owner"] = owner
    (HERE / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved config.json ({len(chosen)} channel(s), owner={'everyone' if not owner else owner}).")

    print("\nAll set. Preview without posting:  python readback.py daily --dry")


def main():
    args = sys.argv[1:]
    dry = "--dry" in args
    mode = next((a for a in args if not a.startswith("-")), "daily")

    if mode == "setup":
        setup()
        return

    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        sys.exit("SLACK_BOT_TOKEN is not set (put it in .env or the environment).")
    if not CFG.get("channels"):
        sys.exit("config.json has no channels. Copy config.example.json and add your channel IDs.")
    client = WebClient(token=token)

    if mode == "loop":
        loop(client)
    elif mode == "weekly":
        run_reminder(client, dry=dry, weekly=True)
    elif mode == "daily":
        # one-shot: treat the current local hour as the slot so reruns within the hour dedupe
        run_reminder(client, dry=dry, slot_hour=_now_local().tm_hour)
    else:
        sys.exit(f"unknown mode '{mode}' (use: setup | daily | weekly | loop, optionally --dry)")


if __name__ == "__main__":
    main()
