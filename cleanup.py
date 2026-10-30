import os
import time
import requests

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CHANNEL_ID = "C0BUE1A3601"

def cleanup_checked_messages():
    if not SLACK_BOT_TOKEN:
        print("SLACK_BOT_TOKEN이 설정되지 않아 삭제 작업을 건너뜁니다.")
        return

    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }

    # 최근 메시지 최대 100건 조회
    history_url = "https://slack.com/api/conversations.history"
    params = {
        "channel": CHANNEL_ID,
        "limit": 100
    }

    res = requests.get(history_url, headers=headers, params=params).json()
    if not res.get("ok"):
        print(f"메시지 목록 조회 실패: {res.get('error')}")
        return

    messages = res.get("messages", [])
    print(f"조회된 최근 메시지 수: {len(messages)}개")

    deleted_count = 0
    for msg in messages:
        ts = msg.get("ts")
        reactions = msg.get("reactions", [])

        # V표시(체크 이모지) 확인
        has_check = any(r.get("name") in ["white_check_mark", "heavy_check_mark", "check"] for r in reactions)

        if has_check:
            delete_url = "https://slack.com/api/chat.delete"
            del_res = requests.post(delete_url, headers=headers, json={"channel": CHANNEL_ID, "ts": ts}).json()
            
            if del_res.get("ok"):
                deleted_count += 1
                print(f"체크 확인된 메시지 삭제 완료 (ts: {ts})")
            else:
                print(f"메시지 삭제 실패 (ts: {ts}): {del_res.get('error')}")
            
            time.sleep(0.5)

    print(f"총 {deleted_count}건의 확인 완료 메시지를 삭제 정리했습니다.")

if __name__ == "__main__":
    cleanup_checked_messages()
