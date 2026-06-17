import os
import sys
import pymysql

# 경로 설정
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_DIR)

from core.config import Config

def sync_devices():
    print("=== Start Devices Sync (FSD -> API DB) ===")
    
    # 1. FSD에서 디바이스 데이터 가져오기
    source_conf = Config.get_source_fsd_config()
    if not source_conf.get('host'):
        print("[Error] Source DB configuration is missing.")
        return

    try:
        source_conn = pymysql.connect(**source_conf)
        with source_conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT seq, device_id, alias, orig_ssaid, orig_adid, orig_idfv, orig_ni, orig_token, memo FROM devices")
            fsd_devices = cursor.fetchall()
        source_conn.close()
        print(f"[FSD] Fetched {len(fsd_devices)} devices.")
    except Exception as e:
        print(f"[FSD] Failed to fetch devices: {e}")
        return

    if not fsd_devices:
        print("No devices to sync.")
        return

    # 2. API DB에 동기화 (Upsert)
    api_conf = Config.get_db_config()
    try:
        api_conn = pymysql.connect(**api_conf, autocommit=True)
        inserted = 0
        updated = 0
        
        with api_conn.cursor() as cursor:
            for dev in fsd_devices:
                sql = """
                    INSERT INTO devices (seq, device_id, alias, orig_ssaid, orig_adid, orig_idfv, orig_ni, orig_token, memo, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'on')
                    ON DUPLICATE KEY UPDATE
                        alias = VALUES(alias),
                        orig_ssaid = VALUES(orig_ssaid),
                        orig_adid = VALUES(orig_adid),
                        orig_idfv = VALUES(orig_idfv),
                        orig_ni = VALUES(orig_ni),
                        orig_token = VALUES(orig_token),
                        memo = VALUES(memo)
                """
                # Execute and count affected rows (1 for insert, 2 for update in MySQL)
                affected = cursor.execute(sql, (
                    dev['seq'], dev['device_id'], dev['alias'], 
                    dev['orig_ssaid'], dev['orig_adid'], dev['orig_idfv'], 
                    dev['orig_ni'], dev['orig_token'], dev['memo']
                ))
                if affected == 1:
                    inserted += 1
                elif affected == 2:
                    updated += 1
                    
        api_conn.close()
        print(f"[API DB] Sync completed: Inserted {inserted}, Updated {updated}.")
    except Exception as e:
        print(f"[API DB] Failed to sync devices: {e}")

if __name__ == "__main__":
    sync_devices()
