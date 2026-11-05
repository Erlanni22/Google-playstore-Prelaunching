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

# 슬랙 사용자 그룹 ID 직접 연동 매핑
SLACK_GROUPS = {
    "GAD1": "<!subteam^S02G8L3148M|gad1>",
    "GAD2": "<!subteam^S0139CGU5U2|gad2>",
    "글로벌": "<!subteam^S0CFL5JD76C|globalads>",
    "globalads": "<!subteam^S0CFL5JD76C|globalads>"
}

DEFAULT_MAPPING = [
    {"keyword": "nexon", "publisher": "NEXON Company", "team": "GAD1", "grade": "S"},
    {"keyword": "mintrocket", "publisher": "민트로켓 (MINTROCKET)", "team": "GAD1", "grade": "S"},
    {"keyword": "neptune", "publisher": "넵튠 (Neptune)", "team": "GAD2", "grade": "S"},
    {"keyword": "devsisters", "publisher": "데브시스터즈", "team": "GAD2", "grade": "S"},
    {"keyword": "krafton", "publisher": "크래프톤 (Krafton)", "team": "GAD2", "grade": "S"},
    {"keyword": "kakaogames", "publisher": "카카오게임즈", "team": "GAD2", "grade": "S"},
    {"keyword": "netmarble", "publisher": "넷마블 (Netmarble)", "team": "GAD2", "grade": "S"},
    {"keyword": "ncsoft", "publisher": "엔씨소프트 (NCSoft)", "team": "GAD2", "grade": "S"},
    {"keyword": "com2us", "publisher": "컴투스 (Com2uS)", "team": "GAD2", "grade": "S"},
    {"keyword": "smilegate", "publisher": "스마일게이트", "team": "GAD2", "grade": "S"},
    {"keyword": "webzen", "publisher": "웹젠 (Webzen)", "team": "GAD2", "grade": "S"},
    {"keyword": "neowiz", "publisher": "네오위즈 (Neowiz)", "team": "GAD2", "grade": "S"},
    {"keyword": "gravity", "publisher": "그라비티 (Gravity)", "team": "GAD2", "grade": "S"},
    {"keyword": "linegames", "publisher": "라인게임즈", "team": "GAD2", "grade": "S"},
    {"keyword": "blizzard", "publisher": "Blizzard Entertainment, Inc.", "team": "GAD2", "grade": "S"},
    {"keyword": "joycity", "publisher": "조이시티(Joycity)", "team": "GAD2", "grade": "A"},
    {"keyword": "wemade", "publisher": "위메이드(Wemade)", "team": "GAD2", "grade": "S"},
    {"keyword": "pearlabyss", "publisher": "펄어비스(Pearl Abyss)", "team": "GAD2", "grade": "S"},
    {"keyword": "shiftup", "publisher": "시프트업 (Shift Up)", "team": "글로벌", "grade": "S"},
    {"keyword": "seasun", "publisher": "어메이징 시선 (Seasun Games)", "team": "글로벌", "grade": "S"},
    {"keyword": "amazingsun", "publisher": "어메이징 시선 (Seasun Games)", "team": "글로벌", "grade": "S"},
    {"keyword": "pawprint", "publisher": "파우프린트 (Pawprint)", "team": "글로벌", "grade": "S"},
    {"keyword": "animo", "publisher": "파우프린트 (Pawprint)", "team": "글로벌", "grade": "S"},
    {"keyword": "yostar", "publisher": "요스타 (Yostar)", "team": "글로벌", "grade": "S"},
    {"keyword": "x.d.", "publisher": "XD (X.D. Network/Global)", "team": "글로벌", "grade": "S"},
    {"keyword": "xd global", "publisher": "XD (X.D. Network/Global)", "team": "글로벌", "grade": "S"},
    {"keyword": "xd entertainment", "publisher": "XD (X.D. Network/Global)", "team": "글로벌", "grade": "S"},
    {"keyword": "xd network", "publisher": "XD (X.D. Network/Global)", "team": "글로벌", "grade": "S"},
    {"keyword": "century games", "publisher": "센추리 게임즈 (Century Games)", "team": "글로벌", "grade": "S"},
    {"keyword": "garena", "publisher": "가레나 (Garena)", "team": "글로벌", "grade": "S"},
    {"keyword": "konami", "publisher": "코나미 (KONAMI)", "team": "글로벌", "grade": "S"},
    {"keyword": "kuro", "publisher": "쿠로게임즈 (Kuro Games)", "team": "글로벌", "grade": "S"},
    {"keyword": "habby", "publisher": "하비 (Habby)", "team": "글로벌", "grade": "S"},
    {"keyword": "lilith", "publisher": "릴리스 게임즈 (Lilith Games)", "team": "글로벌", "grade": "S"},
    {"keyword": "bilibili", "publisher": "빌리빌리 (bilibili)", "team": "글로벌", "grade": "A"},
    {"keyword": "hoyoverse", "publisher": "호요버스 (HoYoverse)", "team": "글로벌", "grade": "S"},
    {"keyword": "cognosphere", "publisher": "호요버스 (HoYoverse)", "team": "글로벌", "grade": "S"},
    {"keyword": "netease", "publisher": "넷이즈 (NetEase)", "team": "글로벌", "grade": "S"},
    {"keyword": "exptional", "publisher": "넷이즈 (NetEase)", "team": "글로벌", "grade": "S"}
]

def load_publisher_db(sh):
    for tab_name in ["시트 DB", "퍼블리셔_DB"]:
        try:
            db_sheet = sh.worksheet(tab_name)
            rows = db_sheet.get_all_values()
            if not rows or len(rows) < 2:
                continue

            header = [re.sub(r'\s+', '', col.lower()) for col in rows[0]]
            kw_idx = next((i for i, h in enumerate(header) if "키워드" in h), -1)
            pub_idx = next((i for i, h in enumerate(header) if "퍼블리셔" in h), -1)
            team_idx = next((i for i, h in enumerate(header) if "팀" in h), -1)
            grade_idx = next((i for i, h in enumerate(header) if "등급" in h), -1)

            if kw_idx == -1:
                continue

            mapping = []
            for r in rows[1:]:
                if len(r) > kw_idx and r[kw_idx].strip():
                    kw = r[kw_idx].strip().lower()
                    pub = r[pub_idx].strip() if pub_idx != -1 and len(r) > pub_idx else kw
                    team = r[team_idx].strip() if team_idx != -1 and len(r) > team_idx else "글로벌"
                    grade = r[grade_idx].strip() if grade_idx != -1 and len(r) > grade_idx else "A"
                    mapping.append({"keyword": kw, "publisher": pub, "team": team, "grade": grade})

            if mapping:
                print(f"'{tab_name}' 탭에서 {len(mapping)}건 로드 완료")
                return mapping
        except Exception:
            continue

    print("기본 내장 매핑 규칙을 사용합니다.")
    return DEFAULT_MAPPING

def infer_publisher_and_team(app_id, developer, email, publisher_db):
    search_target = f"{app_id} {developer} {email}".lower()
    for item in publisher_db:
        if item["keyword"] in search_target:
            return item["publisher"], item["team"], item["grade"], True
    return developer, "글로벌", "C", False

def evaluate_grade(db_grade, is_in_db, email, website, has_trailer):
    if is_in_db:
        if db_grade == "S":
            return "[S] 최우선 영업"
        elif db_grade == "A":
            return "[A] 대형/우선 검토"
        elif db_grade == "B":
            return "[B] 중형/일반 검토"

    email_lower = email.lower()
    is_personal_email = any(d in email_lower for d in ["gmail.com", "naver.com", "hanmail.net", "daum.net", "hotmail
