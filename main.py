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

        msg = (
            f"🚨 *[구글 플레이스토어 신작 알림]* {tag}\n\n"
            f"🎮 *타이틀명*: *{title}*\n"
            f"🏢 *퍼블리셔*: {publisher} (담당: {team})\n"
            f"📅 *출시 예정일*: {release_date}\n"
