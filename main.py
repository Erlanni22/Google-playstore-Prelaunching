import os
import json
import time
import re
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

SHEET_ID = "1uMzoo_Z8qSmEGrTMb6S3Ab1Ct-BvxmxYs8_atTR_dzE" # 본인 구글 시트 ID
GCP_SA_KEY = os.environ.get("GCP_SA_KEY")

# 대형/주요 영업 타겟 개발사 키워드 리스트
MAJOR_PUBLISHERS = [
    "netmable", "netEase", "exptional", "nexon", "kakao", "hoyoverse", "cognosphere",
    "bandai", "tencent", "level infinite", "ujoy", "wanda", "blancozone", "vng",
    "crafton", "com2us", "nhn", "neowiz", "line games", "smilegate", "webzen"
]

def evaluate_grade(developer, email, website, has_trailer):
    dev_lower = developer.lower()
    email_lower = email.lower()
    
    # 1. 주요 대형사 키워드 매칭
    for pub in MAJOR_PUBLISHERS:
        if pub in dev_lower:
            return "[A] 대형/우선영업"
            
    # 2. 기업 도메인 메일 및 마케팅 자산(웹사이트, 영상) 체크
    is_personal_email = any(domain in email_lower for domain in ["gmail.com", "naver.com", "hanmail.net", "daum.net", "hotmail.com"])
    
    if not is_personal_email and email != "없음" and website != "없음" and has_trailer == "O":
        return "[A] 대형/우선영업"
    elif not is_personal_email and email != "없음" and (website != "없음" or has_trailer == "O"):
        return "[B] 중형/검토"
    else:
        return "[C] 일반/인디"

def run():
    print("고도화 사전등록 게임 크롤링을 시작합니다...")
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
                        # 구글 리다이렉트 URL 정제
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
                
                # 6. 영업 등급 자동 계산
                grade = evaluate_grade(developer, email, website, has_trailer)
                
                scraped_data.append([today_str, title, developer, email, website, has_trailer, grade, detail_url])
            except Exception as e:
                print(f"파싱 에러 ({app_id}): {e}")
                
        browser.close()

    if scraped_data:
        creds_dict = json.loads(GCP_SA_KEY)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        
        sh = gc.open_by_key(SHEET_ID)
        
        # 오늘 날짜 탭 가져오기 또는 생성
        try:
            worksheet = sh.worksheet(today_str)
            print(f"기존 탭 '{today_str}'을(를) 사용합니다.")
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=today_str, rows=1000, cols=10)
            print(f"새 탭 '{today_str}'을(를) 생성했습니다.")
        
        # 1행 헤더 세팅 (무조건 1행에 헤더 고정)
        headers = ["수집일자", "타이틀", "개발사/퍼블리셔", "개발자 이메일", "공식 웹사이트", "트레일러 영상", "영업 등급 (자동)", "스토어 링크"]
        
        existing_values = worksheet.get_all_values()
        if len(existing_values) == 0:
            worksheet.append_row(headers)
        elif existing_values[0] != headers:
            # 1행이 헤더와 다를 경우 첫 행 교체
            worksheet.insert_row(headers, index=1)
            
        worksheet.append_rows(scraped_data)
        print(f"🎉 성공: '{today_str}' 탭 1행 헤더 세팅 및 {len(scraped_data)}건 데이터 저장 완료!")

if __name__ == "__main__":
    run()
