import os
import json
import hashlib
import requests
import feedparser
import time
from datetime import datetime

try:
    from facebook_scraper import get_posts
except Exception:
    get_posts = None

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SEEN_FILE = "seen.json"

MAX_RSS_SEND_PER_RUN = 8
MAX_FACEBOOK_SEND_PER_RUN = 3

RSS_FEEDS = [
    "https://www.gundemkibris.com/rss",
    "https://www.kibrispostasi.com/rss",
    "https://www.diyaloggazetesi.com/rss",
    "https://www.yeniduzen.com/rss",
    "https://www.detaykibris.com/rss",
    "https://www.kibrismanset.com/rss",
    "https://www.kibrisgercek.com/rss",
    "https://www.kibristime.com/rss",
    "https://www.nehaberkibris.com/rss",
    "https://www.giynikgazetesi.com/rss",
    "https://www.kibrisadahaber.com/rss",
    "https://www.kibrisgenctv.com/rss",
    "https://kibrisgazetesi.com.tr/rss/",
    "https://www.kibrispostasi.com/feed",
    "https://ubp.org.tr/feed/",
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
    "tatar", "üstel", "erhürman", "özersay", "arıklı", "ataoğlu",
    "basın açıklaması", "duyuru", "bakanlık", "kurum", "parti meclisi",
    "genel başkan", "merkez yönetim", "cumhurbaşkanlığı",
    "başbakanlık", "bakan", "müsteşar", "resmi gazete",
    "seçim", "seçim tarihi", "elektrik kesilecek", "kesinti"
]

IGNORE_KEYWORDS = [
    "magazin", "burç", "astroloji", "reklam", "ilan",
    "spor", "futbol", "basketbol"
]


def log(text):
    print(text, flush=True)


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
        json.dump(list(seen)[-2000:], f, ensure_ascii=False, indent=2)


def make_id(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def clean_text(text):
    if not text:
        return ""
    return " ".join(str(text).replace("\n", " ").replace("\r", " ").split())


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        log("BOT_TOKEN veya CHAT_ID eksik.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": False
            },
            timeout=15
        )

        if response.status_code == 429:
            try:
                wait_time = response.json().get("parameters", {}).get("retry_after", 40)
            except Exception:
                wait_time = 40

            log(f"Telegram limit yedi. {wait_time} saniye bekleniyor.")
            time.sleep(wait_time + 2)
            return send_telegram(message)

        if response.status_code != 200:
            log(f"Telegram hatası: {response.text}")
            return False

        return True

    except Exception as e:
        log(f"Telegram istek hatası: {e}")
        return False


def is_important(title, summary=""):
    text = f"{title} {summary}".lower()

    if any(word in text for word in IGNORE_KEYWORDS):
        return False

    return any(word in text for word in IMPORTANT_KEYWORDS)


def detect_category(title, summary=""):
    text = f"{title} {summary}".lower()

    if any(w in text for w in ["kaza", "yangın", "patlama", "cinayet", "yaralı", "ölü", "polis", "tutuk", "uyuşturucu"]):
        return "🔴 ACİL"

    if any(w in text for w in ["tatar", "üstel", "erhürman", "özersay", "arıklı", "ataoğlu", "hükümet", "meclis", "seçim"]):
        return "🟡 SİYASET"

    if any(w in text for w in ["bm", "5+1", "kıbrıs sorunu", "rum", "ab", "ankara", "atina"]):
        return "🔵 DİPLOMASİ"

    return "⚫ KRİTİK"


def fetch_feed(feed_url):
    try:
        response = requests.get(
            feed_url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 MYK-Radar-Bot"
            }
        )

        if response.status_code != 200:
            log(f"RSS erişim hatası {response.status_code}: {feed_url}")
            return None

        return feedparser.parse(response.content)

    except Exception as e:
        log(f"RSS timeout/hata: {feed_url} - {e}")
        return None


def check_rss(seen):
    new_count = 0

    for feed_url in RSS_FEEDS:
        if new_count >= MAX_RSS_SEND_PER_RUN:
            log("Bu çalıştırmada RSS gönderim limiti doldu.")
            return new_count

        log(f"RSS kontrol ediliyor: {feed_url}")

        feed = fetch_feed(feed_url)

        if not feed:
            continue

        source_name = feed.feed.get("title", feed_url)

        for entry in feed.entries[:6]:
            if new_count >= MAX_RSS_SEND_PER_RUN:
                log("Bu çalıştırmada RSS gönderim limiti doldu.")
                return new_count

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
                log(f"RSS gönderildi: {title}")
                new_count += 1
                time.sleep(2)

    return new_count


def check_facebook(seen):
    if get_posts is None:
        log("Facebook modülü yüklenemedi, atlanıyor.")
        return 0

    new_count = 0

    for account in FACEBOOK_ACCOUNTS:
        if new_count >= MAX_FACEBOOK_SEND_PER_RUN:
            log("Bu çalıştırmada Facebook gönderim limiti doldu.")
            return new_count

        log(f"Facebook kontrol ediliyor: {account['name']}")

        try:
            posts = get_posts(account["id"], pages=1, timeout=10)

            for post in posts:
                text = clean_text(post.get("text") or "")
                post_id = str(post.get("post_id") or "")
                url = post.get("post_url") or f"https://www.facebook.com/{account['id']}"

                if not text and not post_id:
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
                    log(f"Facebook gönderildi: {account['name']}")
                    new_count += 1
                    time.sleep(2)

                break

        except Exception as e:
            log(f"Facebook hatası: {account['name']} - {e}")

    return new_count


def main():
    log("MYK Radar başladı.")

    seen = load_seen()

    rss_count = check_rss(seen)
    fb_count = check_facebook(seen)

    save_seen(seen)

    log(f"Toplam yeni RSS haber: {rss_count}")
    log(f"Toplam yeni Facebook paylaşımı: {fb_count}")
    log("MYK Radar tamamlandı.")


if __name__ == "__main__":
    main()
