import os
import json
import hashlib
import requests
import feedparser
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SEEN_FILE = "seen.json"

RSS_FEEDS = [
    "https://www.gundemkibris.com/rss",
    "https://www.kibrispostasi.com/rss",
    "https://haberkibris.com/rss",
    "https://www.kibrisgazetesi.com/rss",
    "https://www.diyaloggazetesi.com/rss",
]

IMPORTANT_KEYWORDS = [
    "son dakika", "kaza", "trafik kazası", "yangın", "patlama",
    "cinayet", "ölü", "yaralı", "tutuklandı", "tutuklama",
    "mahkeme", "polis", "narkotik", "uyuşturucu", "silahlı",
    "saldırı", "ambulans", "hastane", "grev", "eylem",
    "elektrik kesintisi", "su kesintisi", "ercan", "hükümet",
    "bakanlar kurulu", "başbakan", "cumhurbaşkanı", "meclis",
    "erken seçim", "5+1", "bm", "kıbrıs sorunu",
    "tatar", "üstel", "erhürman", "özersay", "arıklı", "ataoğlu"
]

IGNORE_KEYWORDS = [
    "magazin", "burç", "astroloji", "reklam", "ilan"
]


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-1000:], f, ensure_ascii=False, indent=2)


def make_id(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def clean_text(text):
    if not text:
        return ""
    return " ".join(text.replace("\n", " ").split())


def is_important(title, summary=""):
    text = f"{title} {summary}".lower()

    if any(word in text for word in IGNORE_KEYWORDS):
        return False

    return any(word in text for word in IMPORTANT_KEYWORDS)


def detect_category(title, summary=""):
    text = f"{title} {summary}".lower()

    if any(w in text for w in ["kaza", "yangın", "patlama", "cinayet", "yaralı", "ölü", "polis", "tutuk"]):
        return "🔴 ACİL"

    if any(w in text for w in ["tatar", "üstel", "erhürman", "özersay", "arıklı", "ataoğlu", "hükümet", "meclis", "seçim"]):
        return "🟡 SİYASET"

    if any(w in text for w in ["bm", "5+1", "kıbrıs sorunu", "rum", "ab", "ankara", "atina"]):
        return "🔵 DİPLOMASİ"

    return "⚫ KRİTİK"


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN veya CHAT_ID eksik.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    response = requests.post(url, json=payload, timeout=20)

    if response.status_code != 200:
        print("Telegram hatası:", response.text)
        return False

    return True


def check_feeds():
    seen = load_seen()
    new_count = 0

    for feed_url in RSS_FEEDS:
        print(f"Kontrol ediliyor: {feed_url}")

        try:
            feed = feedparser.parse(feed_url)
            source_name = feed.feed.get("title", feed_url)

            for entry in feed.entries[:10]:
                title = clean_text(entry.get("title", "Başlık yok"))
                link = entry.get("link", "")
                summary = clean_text(entry.get("summary", ""))

                unique_id = make_id(title + link)

                if unique_id in seen:
                    continue

                seen.add(unique_id)

                if not is_important(title, summary):
                    continue

                category = detect_category(title, summary)
                now = datetime.now().strftime("%d.%m.%Y %H:%M")

                short_summary = summary[:220] + "..." if len(summary) > 220 else summary

                message = (
                    f"{category}\n\n"
                    f"<b>{title}</b>\n\n"
                    f"Kaynak: {source_name}\n"
                    f"Saat: {now}\n\n"
                )

                if short_summary:
                    message += f"{short_summary}\n\n"

                message += link

                if send_telegram(message):
                    print(f"Gönderildi: {title}")
                    new_count += 1

        except Exception as e:
            print(f"Feed hatası: {feed_url} - {e}")

    save_seen(seen)
    print(f"Toplam yeni önemli haber: {new_count}")


if __name__ == "__main__":
    check_feeds()
