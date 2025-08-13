import os
import requests
import pytz
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_bitnodes_data():
    url = "https://bitnodes.io/api/v1/snapshots/latest/"
    response = requests.get(url)
    data = response.json()
    return data["nodes"]

def summarize_by_country(nodes):
    from collections import Counter
    countries = [node[7] for node in nodes.values() if node[7]]
    return Counter(countries)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=payload)

def main():
    nodes = get_bitnodes_data()
    total_nodes = len(nodes)
    country_counts = summarize_by_country(nodes)

    # Pakistan local time
    pk_time = datetime.now(pytz.timezone("Asia/Karachi")).strftime("%Y-%m-%d %H:%M:%S")

    message = f"📊 Bitnodes Update — {pk_time} PKT\n"
    message += f"🌐 Total nodes: {total_nodes}\n\n"

    for country, count in country_counts.most_common(15):
        message += f"{country}: {count}\n"

    send_telegram_message(message)

if __name__ == "__main__":
    main()
