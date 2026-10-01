import os
import json
import time
import re
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

SHEET_ID = "1uMzoo_Z8qSmEGrTMb6S3Ab1Ct-BvxmxYs8_atTR_dzE" # 본인 구글 시트 ID
GCP_SA_KEY = os.environ.get("GCP_SA_KEY")

# 개발사/AppID/이메일 기반 퍼블리셔 식별 맵
PUBLISHER_MAPPING = [
    {"keywords": ["hoyoverse", "cognosphere"], "publisher": "호요버스 (HoYoverse)"},
    {"keywords": ["netease", "exptional"], "publisher": "넷이즈 (NetEase)"},
    {"keywords": ["tencent", "level infinite"], "publisher": "텐센트 (Tencent)"},
    {"keywords": ["nexon"], "publisher": "넥슨 (Nexon)"},
    {"keywords": ["netmarble"], "publisher": "넷마블 (Netmarble)"},
    {"keywords": ["kakaogames", "kakao"], "publisher": "카카오게임즈 (Kakao Games)"},
    {"keywords": ["bandainamco", "bandai"], "publisher": "반다이남코 (Bandai Namco)"},
    {"keywords": ["crafton"], "publisher": "크래프톤 (Krafton)"},
    {"keywords": ["com2us"], "publisher": "컴투스 (Com2uS)"},
    {"keywords": ["webzen"], "publisher": "웹젠 (Webzen)"},
    {"keywords": ["ujoy"], "publisher": "유주게임즈/유조이 (Ujoy Games)"},
    {"keywords": ["vng"], "publisher": "VNG Games"},
    {"keywords": ["wanda"], "publisher": "완다 시네마 (Wanda Games)"},
    {"keywords": ["blancozone"], "publisher": "블랑코존 (37Games/Blancozone)"},
    {"keywords": ["gravity"], "publisher": "그라비티 (Gravity)"},
    {"keywords": ["neowiz"], "publisher": "네오위즈 (Neowiz)"},
    {"keywords": ["linegames"], "publisher": "라인게임즈 (Line Games)"},
    {"keywords": ["smilegate"], "publisher": "스마일게이트 (Smilegate)"},
    {"keywords": ["playdigious"], "publisher": "플레이디지어스 (Playdigious)"},
    {"keywords": ["noodlecake"], "publisher": "누들케이크 (Noodlecake)"},
]

def infer_publisher(app_id, developer, email):
    search_target = f"{app_id} {developer} {email}".lower()
    for item in PUBLISHER_MAPPING:
        for kw in item["keywords"]:
            if kw in search_target:
                return item["publisher"]
    # 특별 매핑이 없을 경우 스토어 표기 개발사명 그대로 반환
    return developer

def evaluate_grade(publisher, email, website, has_trailer):
    pub_lower = publisher.lower()
    email_lower = email.lower()
    
    # 1. 퍼블리셔가 식별된 경우 A등급 부여
    for item in PUBLISHER_MAPPING:
        if item["publisher"].lower() in pub_lower:
            return "[A] 대형/우선영업"
            
    # 2. 기업 도메인 메일 및 마케팅 자산 체크
    is_personal_email = any(domain in email_lower for domain in ["gmail.com", "naver.com", "hanmail.net", "daum.net", "hotmail.com"])
    
    if not is_personal_email and email != "없음" and website != "없음" and has_trailer == "O":
        return "[A] 대형/우선영업"
    elif not is_personal_email and email != "없음" and (website != "없음" or has_trailer == "O"):
        return "[B] 중형/검토"
    else:
        return "[C] 일반/인디"

def run():
    print("사전등록 게임 퍼블리셔 매핑 크롤링을 시작합니다...")
    today_str = time.strftime("%Y-%m-%d")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ko-KR")
        page = context.new_page()
        
        url = "https://play.google.com/store/apps/collection/promotion_3000000d51_pre_registration_games?hl=ko&gl=kr"
        page.goto(url, wait_until="networkidle")
        
        # 무한 스크롤
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
                
        print(f"총 {len(app_ids)}개의 사전등록 게임 ID 확보 완료!")
        
        scraped_data = []
        for app_id in app_ids:
            detail_url = f"https://play.google.com/store/apps/details?id={app_id}&hl=ko&gl=kr"
            try:
                page.goto(detail_url, wait_until="networkidle")
                time.sleep(1)
                
                # 1. 타이틀
                title_elem = page.query_selector("h1")
                title = title_elem.inner_text().strip() if title_elem else app_id
                
                # 2. 개발사
                developer = "확인 필요"
                dev_elem = page.query_selector('a[href*="/store/apps/developer"]') or page.query_selector('a[href*="/store/apps/dev?id="]')
                if dev_elem:
                    developer = dev_elem.inner_text().strip()
                
                # 3. 개발자 이메일
                email = "없음"
                email_elem = page.query_selector('a[href^="mailto:"]')
                if email_elem:
                    mail_href = email_elem.get_attribute("href")
                    email = mail_href.replace("mailto:", "").split("?")[0].strip()
                
                # 4. 공식 웹사이트
                website = "없음"
                web_elems = page.query_selector_all('a[href*="http"]')
                for w in web_elems:
                    href = w.get_attribute("href") or ""
                    text = w.inner_text().strip()
                    if "웹사이트" in text or "Website" in text or "방문" in text:
                        if "google.com/url?q=" in href:
                            website = href.split("q=")[1].split("&")[0]
                        else:
                            website = href
                        break
                
                # 5. 트레일러 영상 유무
                has_trailer = "X"
                trailer_elem = page.query_selector('button[aria-label*="트레일러"]') or page.query_selector('button[aria-label*="동영상"]') or page.query_selector('a[href*="youtube.com"]')
                if trailer_elem:
                    has_trailer = "O"
                
                # 6. 상위 퍼블리셔 (컨택 타겟) 추론
                publisher = infer_publisher(app_id, developer, email)
                
                # 7. 영업 등급 자동 산출
                grade = evaluate_grade(publisher, email, website, has_trailer)
                
                scraped_data.append([today_str, title, developer, publisher, email, website, has_trailer, grade, detail_url])
            except Exception as e:
                print(f"파싱 에러 ({app_id}): {e}")
                
        browser.close()

    if scraped_data:
        creds_dict = json.loads(GCP_SA_KEY)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        
        sh = gc.open_by_key(SHEET_ID)
        
        try:
            worksheet = sh.worksheet(today_str)
            print(f"기존 탭 '{today_str}'을(를) 사용합니다.")
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=today_str, rows=1000, cols=10)
            print(f"새 탭 '{today_str}'을(를) 생성했습니다.")
        
        headers = ["수집일자", "타이틀", "개발스튜디오", "상위 퍼블리셔 (컨택 타겟)", "개발자 이메일", "공식 웹사이트", "트레일러 영상", "영업 등급 (자동)", "스토어 링크"]
        
        existing_values = worksheet.get_all_values()
        if len(existing_values) == 0:
            worksheet.append_row(headers)
        elif existing_values[0] != headers:
            worksheet.insert_row(headers, index=1)
            
        worksheet.append_rows(scraped_data)
        print(f"🎉 성공: '{today_str}' 탭에 상위 퍼블리셔 정보 포함 {len(scraped_data)}건 저장 완료!")

if __name__ == "__main__":
    run()
