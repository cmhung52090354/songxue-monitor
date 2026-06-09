import requests
from bs4 import BeautifulSoup
import json
import datetime
import os
import signal

GIST_ID = os.environ["GIST_ID"]
GIST_TOKEN = os.environ["GIST_TOKEN"]

SONGXUE_BASE_URL = "https://booking.taiwantravelmap.com/user/order.aspx"

ROOM_IDS = {
    "7734": "松雪樓精緻兩人房",
    "7735": "松雪樓景觀兩人房",
    "7736": "松雪樓四人房",
}

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("請求逾時")

def parse_available(soup):
    result = []
    for day_div in soup.find_all("div", class_="calendar_date"):
        if "calendar_date_past" in day_div.get("class", []):
            continue
        date_div = day_div.find("div", class_="calendar_date_no")
        price_div = day_div.find("div", class_="calendar_price")
        if not date_div or not price_div:
            continue
        date_num = date_div.get_text(strip=True)
        price_text = price_div.get_text(strip=True)
        if price_text and "NT$" in price_text:
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

def safe_request(session, method, url, timeout=30, **kwargs):
    """帶有 signal timeout 保護的請求"""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)
    try:
        if method == "GET":
            r = session.get(url, timeout=timeout, **kwargs)
        else:
            r = session.post(url, timeout=timeout, **kwargs)
        signal.alarm(0)
        return r
    except TimeoutError:
        signal.alarm(0)
        print(f"  請求超過 {timeout} 秒，強制中止")
        return None
    except Exception as e:
        signal.alarm(0)
        print(f"  請求錯誤: {e}")
        return None

def make_session():
    try:
        import cloudscraper
        s = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        print("使用 cloudscraper")
        return s
    except Exception as e:
        print(f"cloudscraper 失敗: {e}")

    try:
        from curl_cffi import requests as cffi_req
        s = cffi_req.Session(impersonate="chrome120")
        print("使用 curl_cffi")
        return s
    except Exception as e:
        print(f"curl_cffi 失敗: {e}")

    import requests as req
    s = req.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    })
    print("使用一般 requests")
    return s

def scrape_room(r_id):
    url = f"{SONGXUE_BASE_URL}?m=1156&r={r_id}&lg=ch"
    session = make_session()
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Referer": "https://booking.taiwantravelmap.com/",
    }

    now_dt = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    all_available = []

    # 第1個月
    print(f"  抓第1個月...")
    r = safe_request(session, "GET", url, timeout=30, headers=headers)
    if r is None:
        return None
    html = r.text if hasattr(r, 'text') else r.content.decode("utf-8")
    if "cf-error" in html or "Attention Required" in html:
        print(f"  r={r_id} 被 Cloudflare 擋住")
        return None
    soup = BeautifulSoup(html, "html.parser")
    dates1 = parse_available(soup)
    print(f"  第1個月找到 {len(dates1)} 個空房: {dates1}")

    # DEBUG
    if r_id == "7734":
        # 找含有 NT$ 的所有 div
        for d in soup.find_all("div"):
            t = d.get_text(strip=True)
            if "NT$" in t and len(t) < 50:
                print(f"  NT$div class={d.get('class')} text={repr(t)}")
                print(f"  parent class={d.parent.get('class') if d.parent else None}")
                print(f"  parent HTML={str(d.parent)[:300] if d.parent else None}")
                print("  ---")
    
    # end debug    
    
    for d in dates1:
        all_available.append(f"{now_dt.year}/{now_dt.month:02d}/{d}")

    # 第2個月
    print(f"  抓第2個月...")
    post_data = get_all_hidden(soup)
    post_data["__EVENTTARGET"] = "calendar1$lb_Next"
    post_data["__EVENTARGUMENT"] = ""
    r2 = safe_request(session, "POST", url, timeout=30, headers=headers, data=post_data)
    if r2 is None:
        return all_available  # 至少回傳第1個月
    html2 = r2.text if hasattr(r2, 'text') else r2.content.decode("utf-8")
    soup2 = BeautifulSoup(html2, "html.parser")
    dt2 = now_dt + datetime.timedelta(days=31)
    dates2 = parse_available(soup2)
    print(f"  第2個月找到 {len(dates2)} 個空房: {dates2}")
    for d in dates2:
        all_available.append(f"{dt2.year}/{dt2.month:02d}/{d}")

    # 第3個月
    print(f"  抓第3個月...")
    post_data2 = get_all_hidden(soup2)
    post_data2["__EVENTTARGET"] = "calendar1$lb_Next"
    post_data2["__EVENTARGUMENT"] = ""
    r3 = safe_request(session, "POST", url, timeout=30, headers=headers, data=post_data2)
    if r3 is None:
        return all_available  # 至少回傳前2個月
    html3 = r3.text if hasattr(r3, 'text') else r3.content.decode("utf-8")
    soup3 = BeautifulSoup(html3, "html.parser")
    dt3 = now_dt + datetime.timedelta(days=62)
    dates3 = parse_available(soup3)
    print(f"  第3個月找到 {len(dates3)} 個空房: {dates3}")
    for d in dates3:
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
        print(f"  → 共 {len(result['rooms'][name])} 個空房日期")

    update_gist(result)
    print("完成！")
