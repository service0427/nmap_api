import requests
import os
import sys

# Ensure core utils are accessible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.utils import get_kst_date

# LUF 전용 설정
API_URL = "https://lufons.link/api/external/work"

def fetch_data():
    """
    LUF API로부터 데이터를 수집하여 표준 형식으로 반환.
    반환 형식: [{'sid': '...', 'dest_id': '...', 'work_count': ..., 'start_date': '...', 'end_date': '...'}]
    """
    try:
        response = requests.get(API_URL, timeout=10)
        if response.status_code != 200:
            print(f"[LUF] HTTP Error: {response.status_code}")
            return None
        
        data_list = response.json()
        kst_today = get_kst_date().isoformat()
        
        standardized_data = []
        for index, item in enumerate(data_list):
            standardized_data.append({
                'sid': str(index + 1),
                'dest_id': str(item.get('code')),
                'work_count': int(item.get('work_amount', 0)),
                'start_date': kst_today,
                'end_date': kst_today
            })
        
        return standardized_data
    except Exception as e:
        print(f"[LUF] Fetch Exception: {e}")
        return None
