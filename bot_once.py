import os, json, requests
from datetime import datetime, timezone, timedelta

API_URL = "https://bitnodes.io/api/v1/snapshots/latest/"
STATE_FILE = "last_data.json"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Helpers ---------------------------------------------------------------

def fetch_latest():
    r = requests.get(API_URL, timeout=20)
    r.raise_for_status()
    return r.json()

def country_name(alpha2):
    # Full names for ALL ISO 3166-1 alpha-2 codes via pycountry
    # Fallback to the code itself; use 'n/a' for None
    if not alpha2:
        return "n/a"
    try:
        import pycountry
        c = pycountry.countries.get(alpha_2=alpha2)
        return c.name if c else alpha2
    except Exception:
        return alpha2

def summarize_by_country(nodes_dict):
    # Bitnodes “nodes” is a dict: "ip:port" -> [ .., City, CountryCode, Lat, ... ]
    counts = {}
    for arr in nodes_dict.values():
        code = arr[7]  # index 7 (0-based) = country code (per Bitnodes API docs)
        key = code if code else None
        counts[key] = counts.get(key, 0) + 1
    return counts  # keys may be None for Tor/unknown -> we'll show as n/a

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))

def fmt_change(new, old):
    if old is None:
        return ""  # first run for this metric
    diff = new - old
    sign = "+" if diff > 0 else ""
    pct = "" if old == 0 else f", {sign}{(diff/old)*100:.2f}%"
    return f" ({sign}{diff:,}{pct})"

def pkt_now():
    # Pakistan Standard Time = UTC+5 (no DST)
    return (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def send_chunked(text, chunk_size=3800):
    # Telegram max ~4096 chars; be safe and split on line boundaries
    lines, chunk, size = text.splitlines(), [], 0
    for line in lines:
        add = len(line) + 1
        if size + add > chunk_size and chunk:
            send_telegram("\n".join(chunk))
            chunk, size = [], 0
        chunk.append(line)
        size += add
    if chunk:
        send_telegram("\n".join(chunk))

# --- Main ------------------------------------------------------------------

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return

    data = fetch_latest()
    total = data["total_nodes"]
    nodes = data["nodes"]               # dict of "host:port" -> info array
    by_country = summarize_by_country(nodes)

    prev = load_state() or {}
    prev_total = prev.get("total")
    prev_countries = prev.get("countries", {})

    # Build message
    header = f"📊 Bitnodes by Country — {pkt_now()} PKT"
    total_line = f"Total: {total:,}{fmt_change(total, prev_total)}"

    # Sort all countries by node count (desc). Convert None -> "n/a"
    items = []
    for code, count in sorted(by_country.items(), key=lambda x: x[1], reverse=True):
        name = country_name(code) if code else "n/a"
        old = prev_countries.get(code if code else "null")
        items.append(f"• {name}: {count:,}{fmt_change(count, old)}")

    footer = "\nSource: bitnodes.io — snapshot every ~10 min"
    message = "\n".join([header, total_line, *items, footer])

    # Send
    send_chunked(message)

    # Save current state (use 'null' string key for None so JSON keys are stable)
    normalized = { (k if k is not None else "null"): v for k, v in by_country.items() }
    save_state({"total": total, "countries": normalized})

if __name__ == "__main__":
    main()
