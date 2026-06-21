import json
import os
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CHECKED_FILE = "checked_items.json"
LIKE_THRESHOLD = 100

SEARCH_URL = "[booth.pm](https://booth.pm/ja/search/VRChat)"
SEARCH_PARAMS = {
    "max_price": 0,
    "sort": "new",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BoothVRChatNotifier/1.0)"
}


def load_checked_items():
    if os.path.exists(CHECKED_FILE):
        try:
            with open(CHECKED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data)
        except Exception:
            return set()
    return set()


def save_checked_items(items):
    with open(CHECKED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(items), f, ensure_ascii=False, indent=2)


def fetch_search_results():
    response = requests.get(
        SEARCH_URL,
        params=SEARCH_PARAMS,
        headers=HEADERS,
        timeout=20
    )
    response.raise_for_status()
    return response.text


def extract_item_urls(search_html):
    soup = BeautifulSoup(search_html, "html.parser")
    urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r"^[booth](https://booth\.pm/ja/items/\d+$)", href):
            urls.add(href)

    return list(urls)


def fetch_item_detail(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    html = response.text

    title_match = re.search(r"<title>(.*?) - BOOTH</title>", html, re.DOTALL)
    title = title_match.group(1).strip() if title_match else "タイトル不明"

    id_match = re.search(r"/items/(\d+)", url)
    item_id = id_match.group(1) if id_match else url

    like_match = re.search(r'"wishlist_count":\s*(\d+)', html)
    likes = int(like_match.group(1)) if like_match else 0

    shop_match = re.search(r'"shop_name":"(.*?)"', html)
    shop_name = shop_match.group(1) if shop_match else "ショップ不明"

    thumb_match = re.search(r'"thumbnail":"(.*?)"', html)
    image_url = thumb_match.group(1).replace("\\u0026", "&") if thumb_match else ""

    return {
        "id": item_id,
        "title": title,
        "url": url,
        "likes": likes,
        "shop_name": shop_name,
        "image_url": image_url,
    }


def send_discord_notification(item):
    if not DISCORD_WEBHOOK_URL:
        raise ValueError("DISCORD_WEBHOOK_URL が設定されていません")

    embed = {
        "title": f"[無料] {item['title']}",
        "url": item["url"],
        "color": 0x00FF99,
        "fields": [
            {
                "name": "いいね数",
                "value": str(item["likes"]),
                "inline": True
            },
            {
                "name": "ショップ名",
                "value": item["shop_name"],
                "inline": True
            }
        ],
        "footer": {
            "text": "BOOTH VRChat無料商品通知"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    if item["image_url"]:
        embed["thumbnail"] = {"url": item["image_url"]}

    payload = {
        "content": "100いいね以上のVRChat向け無料商品を見つけました。",
        "embeds": [embed]
    }

    response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=20)
    response.raise_for_status()


def main():
    print("チェック開始")

    checked_items = load_checked_items()

    try:
        search_html = fetch_search_results()
        item_urls = extract_item_urls(search_html)
        print(f"検索結果URL数: {len(item_urls)}")
    except Exception as e:
        print(f"検索ページ取得エラー: {e}")
        return

    notified_count = 0

    for url in item_urls[:20]:
        try:
            item = fetch_item_detail(url)
            print(f"確認中: {item['title']} / likes={item['likes']}")
        except Exception as e:
            print(f"商品詳細取得エラー: {url} / {e}")
            continue

        if item["id"] in checked_items:
            continue

        checked_items.add(item["id"])

        if item["likes"] >= LIKE_THRESHOLD:
            try:
                send_discord_notification(item)
                notified_count += 1
                print(f"通知送信: {item['title']}")
            except Exception as e:
                print(f"Discord通知エラー: {e}")

    checked_items = set(list(checked_items)[-500:])
    save_checked_items(checked_items)

    print(f"通知件数: {notified_count}")
    print("チェック終了")


if __name__ == "__main__":
    main()
