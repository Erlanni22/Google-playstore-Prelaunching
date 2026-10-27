import os
import json
import time
import re
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

SHEET_ID = "1uMzoo_Z8qSmEGrTMb6S3Ab1Ct-BvxmxYs8_atTR_dzE"
GCP_SA_KEY = os.environ.get("GCP_SA_KEY")

# 샌드박스 내부 전담 팀 및 퍼블리셔 매핑 룰
PUBLISHER_MAPPING = [
    # 넥슨 전담 팀
    {"keywords": ["nexon", "neptune", "넵튠", "devsisters", "데브시스터즈"], "publisher": "NEXON Company", "team": "NEXON"},
    
    # 국내 게임사 전담 팀
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
    
    # 글로벌 게임사 전담 팀
    {"keywords": ["hoyoverse", "cognosphere"], "publisher": "HoYoverse", "team": "GLOBAL"},
    {"keywords": ["netease", "exptional"], "publisher": "NetEase", "team": "GLOBAL"},
    {"keywords": ["tencent", "level infinite"], "publisher": "Tencent", "team": "GLOBAL"},
    {"keywords": ["bandainamco", "bandai"], "publisher": "Bandai Namco", "team": "GLOBAL"},
    {"keywords": ["ujoy"], "publisher": "Ujoy Games", "team": "GLOBAL"},
    {"keywords": ["vng"], "publisher": "VNG Games", "team": "GLOBAL"},
    {"keywords": ["wanda"], "publisher": "Wanda Games", "team": "GLOBAL"},
    {"keywords": ["blancozone"], "publisher": "Blancozone", "team": "GLOBAL"},
    {"keywords": ["playdigious"], "publisher": "Playdigious", "team": "GLOBAL"},
    {"keywords": ["noodlecake"], "publisher": "Noodlecake", "team": "GLOBAL"},
]

def infer_publisher_and_team(app_id, developer, email):
    search_target = f"{app_id} {developer} {email}".lower()
    for item in PUBLISHER_MAPPING:
        for kw in item["keywords"]:
            if kw in search_target:
                return item["publisher"], item["team"]
    return developer, "GLOBAL"

def evaluate_grade(publisher, email, website, has_trailer):
    pub_lower = publisher.lower()
    email_lower = email.lower()
    
    for item in PUBLISHER_MAPPING:
        if item["publisher"].lower() in pub_lower:
            return "[A] 대형/우선영업"
            
    is_personal_email = any(domain in email_lower for domain in ["gmail.com", "naver.com", "hanmail.net", "daum.net", "hotmail.com"])
    
    if not is_personal_email and email != "없음" and website != "없음" and has_trailer == "O":
        return "[A] 대형/우선영업"
    elif not is_personal_email and email != "없음" and (website != "없음" or has_trailer == "O"):
        return "[B] 중형/검토"
    else:
        return "[C] 일반/인디"

def parse_release_date(page):
    """상세 페이지 내에서 출시 예정일 및 확정일을 정밀 탐색"""
    try:
        # 1. 상단 배너/사전등록 안내 문구 영역 탐색
        body_text = page.locator("body").inner_text()
        
        # 특정 키워드 주변 날짜 패턴 탐색 ("출시 예정일: YYYY년 M월 D일", "2026.MM.DD 출시" 등)
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
                
        # 2. '이 게임 정보' 모달 창 열기 시도 (메타데이터 출시일 탐색)
        info_btn = page.query_selector('button[aria-label*="자세히"]') or page.query_selector('button:has-text("이 게임 정보")')
        if info_btn:
            try:
                info_btn.click(timeout=1000)
                time.sleep(0.5)
                modal_text = page.locator('div[role="dialog"]').inner_text()
                modal_match = re.search(r'출시일[\s\n]+([0-9]{4}\.\s*[0-9]{1,2}\.\s*[0-9]{1,2})', modal_text)
                if modal_match:
                    # 닫기 버튼 누르기
                    close_btn = page.query_selector('button[aria-label*="닫기"]')
                    if close_btn:
                        close_btn.click()
                    return modal_match.group(1).strip() + " (출시 확정)"
            except:
                pass
                
    except Exception as e:
        pass
        
    return "미정 (사전등록 진행 중)"

def run():
    print("사전등록 게임 출시일 정밀 크롤링을 시작합니다...")
    today_str = time.strftime("%Y-%m-%d")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ko-KR")
        page = context.new_page()
        
        url = "https://play.google.com/store/apps/collection/promotion_3000000d51_pre_registration_games?hl=ko&gl=kr"
        page.goto(url, wait_until="networkidle")
        
        # 무한 스크롤 6회
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
                
        print(f"총 {len(app_ids)}개의 사전등록 게임 발견!")
        
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
                
                # 5. 트레일러 영상
                has_trailer = "X"
                trailer_elem = page.query_selector('button[aria-label*="트레일러"]') or page.query_selector('button[aria-label*="동영상"]') or page.query_selector('a[href*="youtube.com"]')
                if trailer_elem:
                    has_trailer = "O"
                
                # 6. 상위 퍼블리셔 및 전담 팀 추론
                publisher, team = infer_publisher_and_team(app_id, developer, email)
                
                # 7. 출시일 정밀 파싱
                release_date = parse_release_date(page)
                
                # 8. 영업 등급
                grade = evaluate_grade(publisher, email, website, has_trailer)
                
                # 데이터 정렬: [수집일자, 타이틀, 개발스튜디오, 상위 퍼블리셔, 출시예정일, 개발자 이메일, 공식 웹사이트, 트레일러, 영업등급, 스토어링크]
                scraped_data.append([
                    today_str, title, developer, publisher, release_date, email, website, has_trailer, grade, detail_url
                ])
            except Exception as e:
                print(f"파싱 에러 ({app_id}): {e}")
                
        browser.close()

    if scraped_data:
        creds_dict = json.loads(GCP_SA_KEY)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        
        sh = gc.open_by_key(SHEET_ID)
        
        # 오늘 날짜 새 탭 생성 또는 기존 탭 초기화 후 재작성
        try:
            worksheet = sh.worksheet(today_str)
            worksheet.clear() # 깔끔한 1행 헤더 정렬을 위해 초기화
            print(f"기존 '{today_str}' 탭을 초기화 후 다시 작성합니다.")
        except gspread.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=today_str, rows=1000, cols=12)
            print(f"새 탭 '{today_str}'을(를) 생성했습니다.")
        
        headers = [
            "수집일자", "타이틀", "개발스튜디오", "상위 퍼블리셔 (컨택 타겟)", 
            "출시예정일", "개발자 이메일", "공식 웹사이트", "트레일러 영상", 
            "영업 등급 (자동)", "스토어 링크"
        ]
        
        worksheet.append_row(headers)
        worksheet.append_rows(scraped_data)
        print(f"🎉 성공: '{today_str}' 탭에 출시일 포함 {len(scraped_data)}건의 정제 데이터 저장 완료!")

if __name__ == "__main__":
    run()
