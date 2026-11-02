import os
import json
import time
import re
import requests
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

SHEET_ID = "1uMzoo_Z8qSmEGrTMb6S3Ab1Ct-BvxmxYs8_atTR_dzE"
GCP_SA_KEY = os.environ.get("GCP_SA_KEY")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CHANNEL_ID = "C0BUE1A3601"

SLACK_TAGS = {
    "NEXON": "<@U_NEXON_LEAD>",
    "DOMESTIC": "<@U_DOMESTIC_LEAD>",
    "GLOBAL": "<@U_GLOBAL_LEAD>"
}

PUBLISHER_MAPPING = [
    {"keywords": ["nexon", "neptune", "넵튠", "devsisters", "데브시스터즈"], "publisher": "NEXON Company", "team": "NEXON"},
    {"keywords": ["krafton", "크래프톤"], "publisher": "Krafton", "team": "DOMESTIC"},
    {"keywords": ["kakaogames", "kakao"], "publisher": "Kakao Games", "team": "DOMESTIC"},
    {"keywords": ["netmarble", "넷마블"], "publisher": "Netmarble", "team": "DOMESTIC"},
    {"keywords": ["ncsoft", "엔씨"], "publisher": "NCSoft", "team": "DOMESTIC"},
    {"keywords": ["com2us"], "publisher": "Com2uS", "team": "DOMESTIC"},
    {"keywords": ["smilegate"], "publisher": "Smilegate", "team": "DOMESTIC"},
    {"keywords": ["neowiz"], "publisher": "Neowiz", "team": "DOMESTIC"},
    {"keywords": ["webzen"], "publisher": "Webzen", "team": "DOMESTIC"},
    {"keywords": ["gravity"], "publisher": "Gravity", "team": "DOMESTIC"},
    {"keywords": ["linegames"], "publisher": "Line Games", "team": "DOMESTIC"},
    {"keywords": ["hoyoverse", "cognosphere"], "publisher": "HoYoverse", "team": "GLOBAL"},
    {"keywords": ["netease", "exptional"], "publisher": "NetEase", "team": "GLOBAL"},
    {"keywords": ["tencent", "level infinite"], "publisher": "Tencent", "team": "GLOBAL"},
    {"keywords": ["bandainamco", "bandai"], "publisher": "Bandai Namco", "team": "GLOBAL"},
    {"keywords": ["ujoy"], "publisher": "Ujoy Games", "team": "GLOBAL"},
    {"keywords": ["vng"], "publisher": "VNG Games", "team": "GLOBAL"},
    {"keywords": ["wanda"], "publisher": "Wanda Games", "team": "GLOBAL"},
    {"keywords": ["blancozone"], "publisher": "Blancozone", "team": "GLOBAL"},
    {"keywords": ["playdigious"], "publisher": "Playdigious", "team": "GLOBAL"},
    {"keywords": ["noodlecake"], "publisher": "Noodlecake", "team": "GLOBAL"}
]

def infer_publisher_and_team(app_id, developer, email):
    search_target = f"{app_id} {developer} {email}".lower()
    for item in PUBLISHER_MAPPING:
        for kw in item["keywords"]:
            if kw in search_target:
                return item["publisher"], item["team"], True
    return developer, "GLOBAL", False

def evaluate_grade(is_known_major, email, website, has_trailer):
    if is_known_major:
        return "[S] 최우선 영업"
    email_lower = email.lower()
    is_personal_email = any(domain in email_lower for domain in ["gmail.com", "naver.com", "hanmail.net", "daum.net", "hotmail.com"])
    if not is_personal_email and email != "없음" and website != "없음" and has_trailer == "O":
        return "[A] 대형/우선 검토"
    elif not is_personal_email and email != "없음" and (website != "없음" or has_trailer == "O"):
        return "[B] 중형/일반 검토"
    else:
        return "[C] 일반/인디"

def parse_release_date(page):
    try:
        body_text = page.locator("body").inner_text()
        patterns = [
            r'(?:출시\s*예정일|출시일|오픈일|런칭일|예상\s*출시일)[\s:]*([0-9]{4}년\s*[0-9]{1,2}월\s*[0-9]{1,2}일)',
            r'(?:출시\s*예정일|출시일|오픈일|런칭일|예상\s*출시일)[\s:]*([0-9]{4}\.\s*[0-9]{1,2}\.\s*[0-9]{1,2})',
            r'(?:출시\s*예정일|출시일|오픈일|런칭일)[\s:]*([0-9]{4}년\s*[1-4]분기)',
            r'([0-9]{4}년\s*[0-9]{1,2}월\s*[0-9]{1,2}일)\s*출시',
            r'([0-9]{4}\.\s*[0-9]{1,2}\.\s*[0-9]{1,2})\s*출시'
        ]
        for pat in patterns:
            match = re.search(pat, body_text)
            if match:
                return match.group(1).strip() + " (출시 확정)"
        info_btn = page.query_selector('button[aria-label*="자세히"]') or page.query_selector('button:has-text("이 게임 정보")')
        if info_btn:
            try:
                info_btn.click(timeout=1000)
                time.sleep(0.5)
                modal_text = page.locator('div[role="dialog"]').inner_text()
                modal_match = re.search(r'출시일[\s\n]+([0-9]{4}\.\s*[0-9]{1,2}\.\s*[0-9]{1,2})', modal_text)
                if modal_match:
                    close_btn = page.query_selector('button[aria-label*="닫기"]')
                    if close_btn:
                        close_btn.click()
                    return modal_match.group(1).strip() + " (출시 확정)"
            except:
                pass
    except:
        pass
    return "미정 (사전등록 진행 중)"

def send_slack_bot_notification(targets):
    if not SLACK_BOT_TOKEN or not targets:
        print("SLACK_BOT_TOKEN 없음 또는 대상 없음")
        return

    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }

    for item in targets:
        title = item["title"]
        publisher = item["publisher"]
        release_date = item["release_date"]
        store_url = item["store_url"]
        team = item["team"]
        tag = SLACK_TAGS.get(team, "")

        text_content = (
            f"🚨 *[S등급 최우선 영업 신작 알림]* {tag}\n\n"
            f"🎮 *타이틀명*: *{title}*\n"
            f"🏢 *퍼블리셔*: {publisher}\n"
            f"📅 *출시 예정일*: {release_date}\n"
            f"🔗 *스토어 링크*: <{store_url}|Google Play 바로가기>\n"
            f"📊 *시트 DB 확인*: <{sheet_url}|주간 사전등록 시트 바로가기>"
        )

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text_content
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ 확인 완료",
                            "emoji": True
                        },
                        "style": "primary",
                        "action_id": "confirm_game_check",
                        "value": title
                    }
                ]
            }
        ]

        try:
            payload = {
                "channel": CHANNEL_ID,
                "text": f"[S등급 신작 알림] {title}",
                "blocks": blocks,
                "unfurl_links": False,
                "unfurl_media": False
            }
            res = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json=payload,
                timeout=10
            ).json()

            if res.get("ok"):
                print(f"발송 성공: {title}")
            else:
                print(f"발송 실패 ({title}): {res.get('error')}")

            time.sleep(1)
        except Exception as e:
            print(f"통신 에러: {e}")

def run():
    print("사전등록 크롤러 및 슬랙 봇 시작...")
    today_str = time.strftime("%Y-%m-%d")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ko-KR")
        page = context.new_page()

        url = "https://play.google.com/store/apps/collection/promotion_3000000d51_pre_registration_games?hl=ko&gl=kr"
        page.goto(url, wait_until="networkidle")

        for i in range(6):
            page.keyboard.press("PageDown")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

        elements = page.query_selector_all('a[href*="/store/apps/details?id="]')
        app_ids = set()
        for elem in elements:
            href = elem.get_attribute("href")
            if href and "id=" in href:
                app_id = href.split("id=")[1].split("&")[0]
                app_ids.add(app_id)

        print(f"사전등록 앱 {len(app_ids)}개 확인")

        scraped_data = []
        slack_targets = []

        for app_id in app_ids:
            detail_url = f"https://play.google.com/store/apps/details?id={app_id}&hl=ko&gl=kr"
            try:
                page.goto(detail_url, wait_until="networkidle")
                time.sleep(1)

                title_elem = page.query_selector("h1")
                title = title_elem.inner_text().strip() if title_elem else app_id

                developer = "확인 필요"
                dev_elem = page.query_selector('a
