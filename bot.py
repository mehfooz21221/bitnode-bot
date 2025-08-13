#!/usr/bin/env python3
import json
import os
import signal
import sys
import time
from collections import Counter
from datetime import datetime
import pytz
import requests

API_URL = "https://bitnodes.io/api/v1/snapshots/latest/"
BOT_API_BASE = "https://api.telegram.org"
STATE_FILE = "state.json"
COUNTRY_CODE_TO_NAME = {
    "US": "United States",
    "DE": "Germany",
    "FR": "France",
    "FI": "Finland",
    "CA": "Canada",
    "NL": "Netherlands",
    "GB": "United Kingdom",
    "CH": "Switzerland",
    "RU": "Russian Federation",
    "AU": "Australia",
    "SG": "Singapore",
    "JP": "Japan",
    "KR": "Korea (Republic of)",
    "CZ": "Czechia",
    "CN": "China",
    "BR": "Brazil",
    "IN": "India",
}
_should_stop = False

def _handle_sig(signum, frame):
    global _should_stop
    _should_stop = True

for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, _handle_sig)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)

def fetch_latest_snapshot():
    r = requests.get(API_URL, headers={"Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()

def summarize_by_country(snapshot):
    nodes = snapshot.get("nodes", {})
    total_nodes = int(snapshot.get("total_nodes") or len(nodes))
    counts = Counter()
    for _addr, arr in nodes.items():
        try:
            cc = arr[7]
        except Exception:
            cc = None
        if not cc:
            continue
        counts[cc] += 1
    return total_nodes, dict(counts)

def pct_change(old, new):
    if old == 0:
        return float('inf') if new > 0 else 0.0
    return (new - old) * 100.0 / old

def human_country(code):
    return COUNTRY_CODE_TO_NAME.get(code, code)

def format_report(ts_utc, total_now, total_prev, by_country_now, by_country_prev, top_n):
    tz = pytz.timezone("Asia/Karachi")
    dt_local = datetime.fromtimestamp(ts_utc, tz)
    items = sorted(by_country_now.items(), key=lambda kv: kv[1], reverse=True)
    top_items = items[:top_n]
    others_count = sum(v for _, v in items[top_n:])
    lines = []
    header = f"📊 Bitnodes by Country — {dt_local.strftime('%Y-%m-%d %H:%M %Z')}\n"
    if total_prev:
        total_delta = total_now - total_prev
        total_pct = pct_change(total_prev, total_now)
        lines.append(f"Total: {total_now:,} ({'+' if total_delta>=0 else ''}{total_delta:,}, {total_pct:.2f}%)")
    else:
        lines.append(f"Total: {total_now:,} (first run)")
    def line_for(code, now, prev):
        delta = now - prev
        pc = pct_change(prev, now)
        sign = '+' if delta >= 0 else ''
        return f"{human_country(code)}: {now:,} ({sign}{delta:,}, {pc if pc!=float('inf') else 100.0:.2f}%)"
    prev = by_country_prev or {}
    for code, count_now in top_items:
        count_prev = prev.get(code, 0)
        lines.append('• ' + line_for(code, count_now, count_prev))
    if others_count:
        others_prev = sum(v for k, v in prev.items() if k not in dict(top_items))
        lines.append('• ' + line_for('Others', others_count, others_prev))
    lines.append("\nSource: bitnodes.io — snapshot every ~10 min")
    return header + "\n".join(lines)

def send_telegram(token, chat_id, text):
    url = f"{BOT_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "HTML",
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("ERROR: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars.", file=sys.stderr)
        sys.exit(1)
    interval = 30  # fixed to 30 minutes
    top_n = 15
    state = load_state()
    print(f"Starting Bitnodes Country Delta Bot — interval={interval}m, top_n={top_n}")
    next_run = 0
    while not _should_stop:
        now = time.time()
        if now >= next_run:
            try:
                snap = fetch_latest_snapshot()
                ts = int(snap.get("timestamp", int(now)))
                total_now, by_cc_now = summarize_by_country(snap)
                prev_entry = state.get("last") or {}
                total_prev = int(prev_entry.get("total", 0))
                by_cc_prev = prev_entry.get("by_cc", {})
                report = format_report(ts, total_now, total_prev, by_cc_now, by_cc_prev, top_n)
                send_telegram(token, chat_id, report)
                state["last"] = {
                    "ts": ts,
                    "total": total_now,
                    "by_cc": by_cc_now,
                }
                save_state(state)
                print(f"Posted update at {datetime.now(pytz.UTC).isoformat()}")
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
            next_run = now + interval * 60
        time.sleep(2)
    print("Shutting down.")

if __name__ == "__main__":
    main()
