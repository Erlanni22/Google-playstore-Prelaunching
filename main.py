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

def load_publisher_db(sh):
    """시트의 '시트 DB' 또는 '퍼블리셔_DB' 탭에서 광고주 마스터 매핑 룰 로드"""
    target_tab_names = ["시트 DB", "퍼블리셔_DB"]
    for tab_name in target_tab_names:
        try:
            db_sheet = sh.worksheet(tab_name)
            records = db_sheet.get_all_records()
            mapping = []
            for r in records:
                kw = str(r.get("키워드 (검색어)", "")).strip().lower()
                pub = str(r.get("정식 퍼블리셔명", "")).strip()
                team = str(r.get("담당 팀", "글로벌")).strip()
                grade = str(r.get("기본 등급", "A")).strip()
                if kw:
                    mapping.append({
                        "keyword": kw,
                        "publisher": pub,
                        "team": team,
                        "grade": grade
                    })
            if mapping:
                print(f"'{tab_name}' 탭에서 {len(mapping)}개의 기준 룰 로드 완료!")
                return mapping
        except Exception:
            continue

    print("⚠️ 시트 DB 탭 로드 실패 시 내장 기본값으로 매핑을 진행합니다.")
    return [
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
    is_personal_email = any(d in email_lower for d in ["gmail.com", "naver.com", "hanmail.net", "daum.net", "hotmail.com"])

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

        info_btn = page.query_selector('button[aria-label*="자세히"]')
        if not info_btn:
            info_btn = page.query_selector('button:has-text("이 게임 정보")')
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

def send_slack_bot_notification(targets, target_sheet_url, today_str):
