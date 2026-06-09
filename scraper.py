import requests
from bs4 import BeautifulSoup
import json
import datetime
import os
from curl_cffi import requests as cffi_req

GIST_ID = os.environ["GIST_ID"]
GIST_TOKEN = os.environ["GIST_TOKEN"]

SONGXUE_BASE_URL = "https://booking.taiwantravelmap.com/user/order.aspx"

ROOM_IDS = {
    "7734": "松雪樓精緻兩人房",
    "7735": "松雪樓景觀兩人房",
    "7736": "松雪樓四人房",
}

def parse_available(soup):
    result = []
    for day_div in soup.find_all("div", class_="every_date"):
        date_div = day_div.find("div", class_="calendar_date_no")
        room_div = day_div.find("div", class_="calendar_room_no")
        if not date_div or not room_div:
            continue
        ds = date_div.find("span")
        if not ds:
            continue
        date_num = ds.text.strip()
        room_text = room_div.get_text(strip=True)
        if room_text and room_text != "無房間" and "NT$" in room_text:
            result.append(date_num)
    return result

def get_all_hidden(soup):
    hidden = {}
    for inp in soup.find_all("input", {"type": "hidden"}):
        name = inp.get("name", "")
        value = inp.get("value", "")
        if name:
            hidden[name] = value
    return hidden

def scrape_room(r_id):
    url = f"{SONGXUE_BASE_URL}?m=1156&r={r_id}&lg=ch"
    session = cffi_req.Session(impersonate="chrome120")
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }

    now_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=8)  # 台灣時間
    all_available = []

    # 第1個月
    r = session.get(url, headers=headers, timeout=60)
    r.encoding = "utf-8"
    if "cf-error" in r.text or "Cloudflare" in r.text:
        print(f"r={r_id} 被 Cloudflare 擋住")
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    for d in parse_available(soup):
        all_available.append(f"{now_dt.year}/{now_dt.month:02d}/{d}")

    # 第2個月
    post_data = get_all_hidden(soup)
    post_data["__EVENTTARGET"] = "calendar1$lb_Next"
    post_data["__EVENTARGUMENT"] = ""
    r2 = session.post(url, data=post_data, headers=headers, timeout=60)
    r2.encoding = "utf-8"
    soup2 = BeautifulSoup(r2.text, "html.parser")
    dt2 = now_dt + datetime.timedelta(days=31)
    for d in parse_available(soup2):
        all_available.append(f"{dt2.year}/{dt2.month:02d}/{d}")

    # 第3個月
    post_data2 = get_all_hidden(soup2)
    post_data2["__EVENTTARGET"] = "calendar1$lb_Next"
    post_data2["__EVENTARGUMENT"] = ""
    r3 = session.post(url, data=post_data2, headers=headers, timeout=60)
    r3.encoding = "utf-8"
    soup3 = BeautifulSoup(r3.text, "html.parser")
    dt3 = now_dt + datetime.timedelta(days=62)
    for d in parse_available(soup3):
        all_available.append(f"{dt3.year}/{dt3.month:02d}/{d}")

    return all_available

def update_gist(data):
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "files": {
            "songxue_status.json": {
                "content": json.dumps(data, ensure_ascii=False, indent=2)
            }
        }
    }
    r = requests.patch(url, headers=headers, json=payload)
    print("Gist 更新結果:", r.status_code)

if __name__ == "__main__":
    now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    result = {"updated_at": now_str, "rooms": {}}

    for r_id, name in ROOM_IDS.items():
        print(f"查詢 {name}...")
        dates = scrape_room(r_id)
        result["rooms"][name] = dates if dates is not None else []
        print(f"  → {len(result['rooms'][name])} 個空房日期")

    update_gist(result)
    print("完成！")
