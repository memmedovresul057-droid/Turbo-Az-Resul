import requests
from bs4 import BeautifulSoup
import time
import re
import os
import threading
from flask import Flask

# --- TELEGRAM MƏLUMATLARI ---
TELEGRAM_BOT_TOKEN = "8846248939:AAF3J7fQztaU4ZLYTklTABqp6vuLTraB8Qk"
TELEGRAM_CHAT_ID = "1442591866"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# --- FİLTR SAZLAMALARI ---
ALLOWED_BRANDS = ["bmw", "mercedes", "benz"]
MAX_PRICE_AZN = 10000

# Proqram başlayanda saytdakı ən son (böyük) ID-ni yadda saxlayacaq
last_max_id = 0

# 1. Render üçün kiçik Veb Server (Port xətasını aradan qaldırmaq üçün)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot 24/7 aktivdir!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    # use_reloader=False arxa fonda thread xətasının qarşısını alır
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Veb serveri arxa fonda (thread) başladırıq
threading.Thread(target=run_flask, daemon=True).start()

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram göndərmə xətası: {e}")

def fetch_ads_page():
    url = "https://turbo.az/autos?q%5Border_filter%5D=created_at"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Saytla bağlantı xətası: {e}")
    return None

def parse_price(price_str):
    if "$" in price_str:
        return None
    digits = re.sub(r"[^\d]", "", price_str)
    return int(digits) if digits else None

def extract_price(ad_soup):
    price_tag = ad_soup.find("div", class_="product-price") or \
                ad_soup.find("span", class_="product-price") or \
                ad_soup.find(class_=lambda x: x and "price" in x.lower())
    if price_tag:
        return price_tag.text.strip().replace("\xa0", " ")
    return "Qiymət qeyd edilməyib"

def is_matching_filter(title, price_str):
    title_lower = title.lower()
    
    # 1. Brend yoxlanışı (BMW / Mercedes)
    brand_match = any(brand in title_lower for brand in ALLOWED_BRANDS)
    if not brand_match:
        return False

    # 2. Qiymət yoxlanışı (<= 10000 AZN)
    price_val = parse_price(price_str)
    if price_val is None or price_val > MAX_PRICE_AZN:
        return False

    return True

def initialize_tracker():
    """Proqram açılan anda saytdakı EN YENİ (ən böyük ID-li) elanın ID-sini tapır"""
    global last_max_id
    soup = fetch_ads_page()
    if not soup:
        print("Saytdan məlumat alınamadı. Yenidən cəhd edilir...")
        return False

    ads = soup.find_all("div", class_="products-i")
    found_ids = []

    for ad in ads:
        link_tag = ad.find("a", class_="products-i__link")
        if link_tag and "href" in link_tag.attrs:
            try:
                ad_id = int(link_tag["href"].split("/")[-1].split("-")[0])
                found_ids.append(ad_id)
            except ValueError:
                continue

    if found_ids:
        last_max_id = max(found_ids)
        print(f"✅ Sistem aktivləşdirildi!")
        print(f"📌 Baza üçün ən son elan ID-si götürüldü: {last_max_id}")
        send_telegram_message("🎯 <b>Turbo.az Son Dəqiqə İzləyicisi Başladı!</b>\nYalnız <b>son dəqiqələrdə</b> paylaşılan BMW/Mercedes (≤ 10,000 AZN) elanları gələcək.")
        print("⏳ Tamamilə yeni elanlar gözlənilir (köhnə/yenilənmiş elanlar atılmayacaq)...\n")
        return True
    return False

def check_for_new_ads():
    global last_max_id
    soup = fetch_ads_page()
    if not soup:
        return

    ads = soup.find_all("div", class_="products-i")
    new_ads = []

    for ad in ads:
        link_tag = ad.find("a", class_="products-i__link")
        if not link_tag or "href" not in link_tag.attrs:
            continue

        try:
            ad_link = "https://turbo.az" + link_tag["href"]
            ad_id = int(ad_link.split("/")[-1].split("-")[0])
        except ValueError:
            continue

        # CRITICAL RULE: Yalnız bazadakı son ID-dən daha BÖYÜK olan (yəni son dəqiqələrdə dərc edilmiş) elanlar alınır
        if ad_id > last_max_id:
            title_tag = ad.find("div", class_="products-i__name") or ad.find("span", class_="products-i__name")
            title = title_tag.text.strip() if title_tag else "Model qeyd edilməyib"
            price = extract_price(ad)

            # Brend və qiymət şərtini yoxlayırıq
            if is_matching_filter(title, price):
                new_ads.append({
                    "id": ad_id,
                    "title": title,
                    "price": price,
                    "link": ad_link
                })

    if new_ads:
        # ID-yə görə kiçikdən böyüyə sıralayırıq (ən birinci paylaşılan birinci gəlsin)
        new_ads.sort(key=lambda x: x["id"])
        
        for ad in new_ads:
            print(f"🔥 YENİ SON DƏQİQƏ ELANI: {ad['title']} - {ad['price']}")
            
            tg_message = (
                f"🚨 <b>YENİ SON DƏQİQƏ ELANI!</b>\n\n"
                f"🚘 <b>Model:</b> {ad['title']}\n"
                f"💰 <b>Qiymət:</b> {ad['price']}\n"
                f"🆔 <b>ID:</b> {ad['id']}\n\n"
                f"🔗 {ad['link']}"
            )
            send_telegram_message(tg_message)

        # Ən son gördüyümüz ID-ni yeniləyirik
        last_max_id = max(ad["id"] for ad in new_ads)

if __name__ == "__main__":
    while not initialize_tracker():
        time.sleep(3)

    while True:
        try:
            check_for_new_ads()
            time.sleep(10)
        except KeyboardInterrupt:
            print("\nİzləmə dayandırıldı.")
            break
        except Exception as e:
            print(f"Xəta: {e}")
            time.sleep(10)
