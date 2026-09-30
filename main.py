import os
import json
import time
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

SHEET_ID = "1uMzoo_Z8qSmEGrTMb6S3Ab1Ct-BvxmxYs8_atTR_dzE" # 본인 구글 시트 ID
GCP_SA_KEY = os.environ.get("GCP_SA_KEY")

def run():
    print("사전등록 게임 크롤링을 시작합니다...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ko-KR")
        page = context.new_page()
        
        url = "https://play.google.com/store/apps/collection/promotion_3000000d51_pre_registration_games?hl=ko&gl=kr"
        page.goto(url, wait_until="networkidle")
        
        # 무한 스크롤 내려서 전체 목록 로딩
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
                time.sleep(1) # 동적 텍스트 렌더링 대기
                
                # 1. 타이틀 추출
                title_elem = page.query_selector("h1")
                title = title_elem.inner_text().strip() if title_elem else app_id
                
                # 2. 개발사 추출 (다중 조건 탐색)
                developer = "확인 필요"
                dev_elem = page.query_selector('a[href*="/store/apps/developer"]')
                if not dev_elem:
                    dev_elem = page.query_selector('a[href*="/store/apps/dev?id="]')
                
                if dev_elem:
                    developer = dev_elem.inner_text().strip()
                else:
                    meta_dev = page.query_selector('meta[name="author"]') or page.query_selector('meta[itemprop="author"]')
                    if meta_dev:
                        developer = meta_dev.get_attribute("content") or "확인 필요"
                
                today = time.strftime("%Y-%m-%d")
                scraped_data.append([today, title, developer, "사전등록 중", detail_url])
            except Exception as e:
                print(f"파싱 에러 ({app_id}): {e}")
                
        browser.close()

    if scraped_data:
        creds_dict = json.loads(GCP_SA_KEY)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.get_worksheet(0)
        
        if len(worksheet.get_all_values()) == 0:
            worksheet.append_row(["수집일자", "타이틀", "개발사/퍼블리셔", "출시예정일", "스토어 링크"])
            
        worksheet.append_rows(scraped_data)
        print(f"🎉 성공: 구글 시트에 {len(scraped_data)}건의 데이터가 업데이트되었습니다!")

if __name__ == "__main__":
    run()
