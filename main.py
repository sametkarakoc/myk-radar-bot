import os
import json
import hashlib
import requests
import feedparser
from datetime import datetime
from facebook_scraper import get_posts

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

FACEBOOK_ACCOUNTS = [
    {"name": "Polis Basın Subaylığı", "id": "kktc.pgm", "category": "⚫ POLİS"},
    {"name": "Ünal Üstel", "id": "unal.ustel.9", "category": "🟡 SİYASET"},
    {"name": "Tufan Erhürman", "id": "tufan.erhurman", "category": "🟡 SİYASET"},
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

IGNORE_KEYWORDS = ["magazin", "burç", "astroloji", "reklam", "ilan"]


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
        json.dump(list(seen)[-1500:], f, ensure_ascii=False, indent=2)


def make_id(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def clean_text(text):
    if not text:
        return ""

    text = str(text)
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    return " ".join(text.split())


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN veya CHAT_ID eksik.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": False
    }

    try:
        response = requests.post(url, json=payload, timeout=20)

        if response.status_code != 200:
            print("Telegram hatası:", response.text)
            return False

        return True

    except Exception as e:
        print("Telegram istek hatası:", e)
        return False


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


def check_rss(seen):
    new_count = 0

    for feed_url in RSS_FEEDS:
        print(f"RSS kontrol ediliyor: {feed_url}")

        try:
            feed = feedparser.parse(feed_url)
            source_name = feed.feed.get("title", feed_url)

            for entry in feed.entries[:10]:
                title = clean_text(entry.get("title", "Başlık yok"))
                link = entry.get("link", "")
                summary = clean_text(entry.get("summary", ""))

                unique_id = make_id("rss-" + title + link)

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
                    f"{title}\n\n"
                    f"Kaynak: {source_name}\n"
                    f"Saat: {now}\n\n"
                )

                if short_summary:
                    message += f"{short_summary}\n\n"

                message += link

                if send_telegram(message):
                    print(f"RSS gönderildi: {title}")
                    new_count += 1

        except Exception as e:
            print(f"RSS hatası: {feed_url} - {e}")

    return new_count


def check_facebook(seen):
    new_count = 0

    for account in FACEBOOK_ACCOUNTS:
        print(f"Facebook kontrol ediliyor: {account['name']}")

        try:
            posts = get_posts(account["id"], pages=2)

            for post in posts:
                post_id = str(post.get("post_id") or "")
                text = clean_text(post.get("text") or "")
                url = post.get("post_url") or f"https://www.facebook.com/{account['id']}"

                if not post_id and not text:
                    continue

                unique_id = make_id("fb-" + account["id"] + post_id + text[:100])

                if unique_id in seen:
                    continue

                seen.add(unique_id)

                short_text = text[:500] + "..." if len(text) > 500 else text
                now = datetime.now().strftime("%d.%m.%Y %H:%M")

                message = (
                    f"{account['category']}\n\n"
                    f"{account['name']} yeni paylaşım yaptı\n\n"
                    f"Saat: {now}\n\n"
                )

                if short_text:
                    message += f"{short_text}\n\n"

                message += url

                if send_telegram(message):
                    print(f"Facebook gönderildi: {account['name']}")
                    new_count += 1

                break

        except Exception as e:
            print(f"Facebook hatası: {account['name']} - {e}")

    return new_count


def main():
    seen = load_seen()

    rss_count = check_rss(seen)
    fb_count = check_facebook(seen)

    save_seen(seen)

    print(f"Toplam yeni RSS haber: {rss_count}")
    print(f"Toplam yeni Facebook paylaşımı: {fb_count}")


if __name__ == "__main__":
    main()
