import requests
import os
import sys

# Ensure core utils are accessible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.utils import get_kst_date

# LUF 전용 설정
API_URL = "https://lufons.link/api/external/work"

IS_DAILY_ONLY = True

def fetch_data():
    """
    LUF API로부터 데이터를 수집하여 표준 형식으로 반환.
    반환 형식: [{'sid': '...', 'dest_id': '...', 'search_keyword': '', 'target_url': '...', 'work_count': ..., 'start_date': '...', 'end_date': '...'}]
    """
    try:
        response = requests.get(API_URL, timeout=10)
        if response.status_code != 200:
            print(f"[LUF] HTTP Error: {response.status_code}")
            return None
        
        data_list = response.json()
        kst_today = get_kst_date()
        kst_today_iso = kst_today.isoformat()
        kst_date_str = kst_today.strftime("%Y%m%d")
        
        standardized_data = []
        for index, item in enumerate(data_list):
            code = str(item.get('code'))
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
        print(f"[LUF] Fetch Exception: {e}")
        return None
