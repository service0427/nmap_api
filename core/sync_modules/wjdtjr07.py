import requests
import os
import sys

# Ensure core utils are accessible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.utils import get_kst_date

# WJDTJR07 전용 설정
API_URL = "https://wjdtjr07.link/api/external/work"

IS_DAILY_ONLY = True

def fetch_data():
    """
    WJDTJR07 API로부터 데이터를 수집하여 표준 형식으로 반환.
    반환 형식: [{'sid': '...', 'dest_id': '...', 'search_keyword': '', 'target_url': '...', 'work_count': ..., 'start_date': '...', 'end_date': '...'}]
    """
    try:
        kst_today = get_kst_date()
        kst_today_iso = kst_today.isoformat()
        kst_date_str = kst_today.strftime("%Y%m%d")
        
        url = f"{API_URL}?date={kst_today_iso}"
        print(f"[WJDTJR07] Fetching data from: {url}")
        
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            print(f"[WJDTJR07] HTTP Error: {response.status_code}")
            return None
        
        data_list = response.json()
        if not isinstance(data_list, list):
            print(f"[WJDTJR07] Invalid API response format: expected list, got {type(data_list)}")
            return None
            
        if len(data_list) == 0:
            print("[WJDTJR07] Sync aborted: API returned 0 items. Treating as temporary failure to retry.")
            return None
            
        standardized_data = []
        for index, item in enumerate(data_list):
            code = str(item.get('code'))
            if not code or code == 'None':
                continue
            slot_id = f"{kst_date_str}{index + 1:05d}"
            standardized_data.append({
                'sid': int(slot_id),   # BIGINT 정수형 컬럼 대응
                'dest_id': code,
                'search_keyword': '',  # API 소스는 검색어가 없으므로 빈 값 (엔진에서 places.name으로 자동 보완)
                'target_url': f"https://m.place.naver.com/place/{code}",
                'work_count': int(item.get('work_amount', 0)),
                'start_date': kst_today_iso,
                'end_date': kst_today_iso
            })
        
        return standardized_data
    except Exception as e:
        print(f"[WJDTJR07] Fetch Exception: {e}")
        return None
