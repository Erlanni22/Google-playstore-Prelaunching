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

# 슬랙 사용자 그룹 ID 매핑
SLACK_GROUPS = {
    "GAD1": "<!subteam^S02G8L3148M|gad1>",
    "GAD2": "<!subteam^S0139CGU5U2|gad2>",
    "글로벌": "<!subteam^S0CFL5JD76C|globalads>",
    "globalads": "<!subteam^S0CFL5JD76C|globalads>"
}

DEFAULT_MAPPING = [
    {"kw": "nexon", "pub": "NEXON Company", "team": "GAD1", "grade": "S"},
    {"kw": "mintrocket", "pub": "민트로켓 (MINTROCKET)", "team": "GAD1", "grade": "S"},
    {"kw": "neptune", "pub": "넵튠 (Neptune)", "team": "GAD2", "grade": "S"},
    {"kw": "devsisters", "pub": "데브시스터즈", "team": "GAD2", "grade": "S"},
    {"kw": "krafton", "pub": "크래프톤 (Krafton)", "team": "GAD2", "grade": "S"},
    {"kw": "kakaogames", "pub": "카카오게임즈", "team": "GAD2", "grade": "S"},
    {"kw": "netmarble", "pub": "넷마블 (Netmarble)", "team": "GAD2", "grade": "S"},
    {"kw": "ncsoft", "pub": "엔씨소프트 (NCSoft)", "team": "GAD2", "grade": "S"},
    {"kw": "com2us", "pub": "컴투스 (Com2uS)", "team": "GAD2", "grade": "S"},
    {"kw": "smilegate", "pub": "스마일게이트", "team": "GAD2", "grade": "S"},
    {"kw": "webzen", "pub": "웹젠 (Webzen)", "team": "GAD2", "grade": "S"},
    {"kw": "neowiz", "pub": "네오위즈 (Neowiz)", "team": "GAD2", "grade": "S"},
    {"kw": "gravity", "pub": "그라비티 (Gravity)", "team": "GAD2", "grade": "S"},
    {"kw": "linegames", "pub": "라인게임즈", "team": "GAD2", "grade": "S"},
    {"kw": "blizzard", "pub": "Blizzard Entertainment", "team": "GAD2", "grade": "S"},
    {"kw": "joycity", "pub": "조이시티(Joycity)", "team": "GAD2", "grade": "A"},
    {"kw": "wemade", "pub": "위메이드(Wemade)", "team": "GAD2", "grade": "S"},
    {"kw": "pearlabyss", "pub": "펄어비스(Pearl Abyss)", "team": "GAD2", "grade": "S"},
    {"kw": "shiftup", "pub": "시프트업 (Shift Up)", "team": "글로벌", "grade": "S"},
    {"kw": "seasun", "pub": "어메이징 시선 (Seasun)", "team": "글로벌", "grade": "S"},
    {"kw": "amazingsun", "pub": "어메이징 시선", "team": "글로벌", "grade": "S"},
    {"kw": "pawprint", "pub": "파우프린트 (Pawprint)", "team": "글로벌", "grade": "S"},
    {"kw": "animo", "pub": "파우프린트 (Pawprint)", "team": "글로벌", "grade": "S"},
    {"kw": "yostar", "pub": "요스타 (Yostar)", "team": "글로벌", "grade": "S"},
    {"kw": "x.d.", "pub": "XD (X.D. Network/Global)", "team": "글로벌", "grade": "S"},
    {"kw": "xd global", "pub": "XD (X.D. Network/Global)", "team": "글로벌", "grade": "S"},
    {"kw": "xd entertainment", "pub": "XD", "team": "글로벌", "grade": "S"},
    {"kw": "xd network", "pub": "XD Network", "team": "글로벌", "grade": "S"},
    {"kw": "century games", "pub": "센추리 게임즈", "team": "글로벌", "grade": "S"},
    {"kw": "garena", "pub": "가레나 (Garena)", "team": "글로벌", "grade": "S"},
    {"kw": "konami", "pub": "코나미 (KONAMI)", "team": "글로벌", "grade": "S"},
    {"kw": "kuro", "pub": "쿠로게임즈", "team": "글로벌", "grade": "S"},
    {"kw": "habby", "pub": "하비 (Habby)", "team": "글로벌", "grade": "S"},
    {"kw": "lilith", "pub": "릴리스 게임즈", "team": "글로벌", "grade": "S"},
    {"kw": "bilibili", "pub": "빌리빌리 (bilibili)", "team": "글로벌", "grade": "A"},
    {"kw": "hoyoverse", "pub": "호요버스 (HoYoverse)", "team": "글로벌", "grade": "S"},
    {"kw": "cognosphere", "pub": "호요버스", "team": "글로벌", "grade": "S"},
    {"kw": "netease", "pub": "넷이즈 (NetEase)", "team": "글로벌", "grade": "S"},
    {"kw": "exptional", "pub": "넷이즈", "team": "글로벌", "grade": "S"}
]

def load_publisher_db(sh):
    for tab in ["시트 DB", "퍼블리셔_DB"]:
        try:
            ws = sh.worksheet(tab)
            data = ws.get_all_values()
            if len(data) < 2:
                continue
            mapping = []
            for r in data[1:]:
                if len(r) >= 4 and r[0].strip():
                    mapping.append({
                        "kw": r[0].strip().lower(),
                        "pub": r[1].strip(),
                        "team": r[2].strip(),
                        "grade": r[3].strip()
                    })
            if mapping:
                print(f"'{tab}' 탭에서 {len(mapping)}건 로드 성공")
                return mapping
        except Exception:
            pass
    print("내장 기본 매핑 규칙 사용")
    return DEFAULT_MAPPING

def infer_publisher_and_team(app_id, developer, email, publisher_db):
    target = f"{app_id} {developer} {email}".lower()
    for item in publisher_db:
        if item["kw"] in target:
            return item["pub"], item["team"], item["grade"], True
    return developer, "글로벌", "C", False

def evaluate_grade(db_grade, is_in_db, email, website, has_trailer):
    if is_in_db:
        if db_grade == "S":
            return "[S] 최우선 영업"
        if db_grade == "A":
            return "[A] 대형/우선 검토"
        return "[B] 중형/일반 검토"

    em = email.lower()
    free_domains = ["gmail", "naver", "daum", "hanmail", "hotmail"]
    is_personal = any(d in em for d in free_domains)

    if not is_personal and email != "없음" and website != "없음" and has_trailer == "O":
        return "[A] 대형/우선 검토"
    elif not is_personal and email != "없음":
        return "[B] 중형/일반 검토"
    return "[C] 일반/인디"

def parse_release_date(page):
    try:
        body = page.locator("body").inner_text()
        patterns = [
            r'([0-9]{4}년\s*[0-9]{1,2}월\s*[0-9]{1,2}일)',
            r'([0-9]{4}\.\s*[0-9]{1,2}\.\s*[0-9]{1,2})',
            r'([0-9]{4}년\s*[1-4]분기)'
        ]
        for p in patterns:
            m = re.search(p, body)
            if m:
                return m.group(1).strip() + " (출시 확정)"
    except Exception:
        pass
    return "미정 (사전등록 진행 중)"

def send_slack_bot_notification(targets, sheet_url, today_str):
    if not SLACK_BOT_TOKEN or not targets:
        return

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
        tag = SLACK_GROUPS.get(team, f"@{team}")

        lines = [
            f"🚨 *[구글 플레이스토어 신작 알림]* {tag}",
            "",
            f"🎮 *타이틀명*: *{title}*",
            f"🏢 *퍼블리셔*: {publisher} (담당: {team})",
            f"📅 *출시 예정일*: {release_date}",
            f"🔗 *스토어 링크*: <{store_url}|Google Play 바로가기>",
            f"📊 *시트 DB 확인*: <{sheet_url}|{today_str} 신규 탭 바로가기>",
            "",
            "👉 _확인 완료 시 이 메시지에 :white_check_mark:(✅) 이모지를 달아주세요._"
        ]
        msg = "\n".join(lines)

        try:
            requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={
                    "channel": CHANNEL_ID,
                    "text": msg,
                    "unfurl_links": False,
                    "unfurl_media": False
                },
                timeout=10
            )
            time.sleep(1)
        except Exception as e:
            print(f"슬랙 전송 예외: {e}")

def run():
    print("사전등록 수집 및 알림 시작...")
    today_str = time.strftime("%Y-%m-%d")

    creds_dict = json.loads(GCP_SA_KEY)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    publisher_db = load_publisher_db(sh)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ko-KR")
        page = context.new_page()

        url = "https://play.google.com/store/apps/collection/promotion_3000000d51_pre_registration_games?hl=ko&gl=kr"
        page.goto(url, wait_until="networkidle")

        for _ in range(6):
            page.keyboard.press("PageDown")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

        elems = page.query_selector_all('a[href*="/store/apps/details?id="]')
        app_ids = set()
        for el in elems:
            href = el.get_attribute("href")
            if href and "id=" in href:
                app_ids.add(href.split("id=")[1].split("&")[0])

        print(f"사전등록 앱 {len(app_ids)}개 발견")

        scraped_data = []
        slack_targets = []

        for app_id in app_ids:
            detail_url = f"https://play.google.com/store/apps/details?id={app_id}&hl=ko&gl=kr"
            try:
                page.goto(detail_url, wait_until="networkidle")
                time.sleep(1)

                t_el = page.query_selector("h1")
                title = t_el.inner_text().strip() if t_el else app_id

                dev = "확인 필요"
                d_el = page.query_selector('a[href*="/store/apps/developer"]')
                if not d_el:
                    d_el = page.query_selector('a[href*="/store/apps/dev?id="]')
                if d_el:
                    dev = d_el.inner_text().strip()

                email = "없음"
                m_el = page.query_selector('a[href^="mailto:"]')
                if m_el:
                    email = m_el.get_attribute("href").replace("mailto:", "").split("?")[0].strip()

                website = "없음"
                w_els = page.query_selector_all('a[href*="http"]')
                for w in w_els:
                    txt = w.inner_text().strip()
                    if any(k in txt for k in ["웹사이트", "Website", "방문"]):
                        hr = w.get_attribute("href") or ""
                        website = hr.split("q=")[1].split("&")[0] if "google.com/url?q=" in hr else hr
                        break

                trailer = "X"
                tr_el = page.query_selector('button[aria-label*="트레일러"]')
                if not tr_el:
                    tr_el = page.query_selector('button[aria-label*="동영상"]')
                if not tr_el:
                    tr_el = page.query_selector('a[href*="youtube.com"]')
                if tr_el:
                    trailer = "O"

                pub, team, db_grade, in_db = infer_publisher_and_team(app_id, dev, email, publisher_db)
                r_date = parse_release_date(page)
                grade = evaluate_grade(db_grade, in_db, email, website, trailer)

                if "[S]" in grade:
                    slack_targets.append({
                        "title": title,
                        "publisher": pub,
                        "release_date": r_date,
                        "store_url": detail_url,
                        "team": team
                    })

                scraped_data.append([
                    today_str, title, dev, pub, team, r_date, email, website, trailer, grade, detail_url
                ])
            except Exception as e:
                print(f"파싱 건너뜀 ({app_id}): {e}")

        browser.close()

    if scraped_data:
        try:
            worksheet = sh.worksheet(today_str)
            worksheet.clear()
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=today_str, rows=1000, cols=12)

        target_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={worksheet.id}"

        headers = [
            "수집일자", "타이틀", "개발스튜디오", "상위 퍼블리셔 (컨택 타겟)", "담당 팀",
            "출시예정일", "개발자 이메일", "공식 웹사이트", "트레일러 영상", 
            "영업 등급 (자동)", "스토어 링크"
        ]

        worksheet.append_row(headers)
        worksheet.append_rows(scraped_data)
        print(f"'{today_str}' 탭에 {len(scraped_data)}건 기록 완료! (gid: {worksheet.id})")

        if slack_targets:
            print(f"[S등급] {len(slack_targets)}건 슬랙 발송 시작...")
            send_slack_bot_notification(slack_targets, target_url, today_str)
            print("발송 완료!")

if __name__ == "__main__":
    run()
