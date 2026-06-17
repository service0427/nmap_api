import pymysql
import os
import sys
from datetime import date

# Ensure core utils are accessible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import Config
from core.utils import get_kst_date

def fetch_data():
    """
    FSD (Source DB)로부터 데이터를 수집하여 표준 형식으로 반환.
    조건:
    1. success_count = 0 (성공 기록 없음)
    2. fail_count > 2 (실패가 많이 쌓임)
    3. status = 'on' (현재 활성 상태)
    4. expiry_date >= today (만료되지 않음)
    """
    try:
        conf = Config.get_source_fsd_config()
        if not conf.get('host'):
            print("[FSD] Skip: Source DB configuration missing.")
            return None
            
        conn = pymysql.connect(**conf)
        kst_today = get_kst_date()
        
        with conn.cursor() as cursor:
            # JOIN query with new filters: success_count=0 AND fail_count > 2
            sql = """
                SELECT d.seq, d.dest_id, d.daily_limit, d.start_date, d.expiry_date 
                FROM destinations d
                INNER JOIN daily_tasks dt ON d.dest_id = dt.dest_id
                WHERE dt.success_count = 0
                  AND dt.fail_count > 2
                  AND d.status = 'on'
                  AND d.expiry_date >= %s
            """
            cursor.execute(sql, (kst_today,))
            rows = cursor.fetchall()
        conn.close()
        
        standardized_data = []
        for item in rows:
            standardized_data.append({
                'sid': str(item['seq']),
                'dest_id': str(item['dest_id']),
                'work_count': int(item['daily_limit'] or 0),
                'start_date': item['start_date'].isoformat() if item['start_date'] else kst_today.isoformat(),
                'end_date': item['expiry_date'].isoformat() if item['expiry_date'] else "2030-12-31"
            })
            
        print(f"[FSD] Fetched {len(standardized_data)} high-priority failures for KST {kst_today}.")
        return standardized_data
    except Exception as e:
        print(f"[FSD] Fetch Exception: {e}")
        return None
