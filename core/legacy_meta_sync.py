import pymysql
import sys
import os

# Path adjustment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import Config

def sync_legacy_metadata():
    print("=== Starting Legacy Metadata Shadow Sync (Old -> New) ===")
    
    legacy_conf = Config.get_source_fsd_config()
    local_conf = Config.get_db_config()
    
    try:
        legacy_conn = pymysql.connect(**legacy_conf)
        local_conn = pymysql.connect(**local_conf, autocommit=True)
        
        with legacy_conn.cursor(pymysql.cursors.DictCursor) as leg_cur:
            # 1. Sync Device Metadata (Memo, Status)
            print("[1/2] Syncing Device Metadata...")
            leg_cur.execute("SELECT device_id, memo, status FROM devices")
            leg_devices = leg_cur.fetchall()
            
            with local_conn.cursor() as loc_cur:
                for d in leg_devices:
                    # Update local device info if it exists
                    loc_cur.execute("""
                        UPDATE devices 
                        SET memo = %s, status = %s 
                        WHERE device_id = %s
                    """, (d['memo'], d['status'], d['device_id']))
            print(f"      - {len(leg_devices)} devices updated.")

            # 2. Sync Destination Metadata (users as 'test' flag)
            print("[2/2] Syncing Destination Tags...")
            # We treat 'users' column as our site_id or test flag
            leg_cur.execute("SELECT dest_id, users FROM destinations")
            leg_dests = leg_cur.fetchall()
            
            with local_conn.cursor() as loc_cur:
                for dest in leg_dests:
                    site_val = 'test' if dest['users'] == 'test' else 'FSD'
                    # We store this in raw_slots.site_id to match our allocation logic
                    loc_cur.execute("""
                        UPDATE raw_slots 
                        SET site_id = %s 
                        WHERE dest_id = %s
                    """, (site_val, dest['dest_id']))
            print(f"      - {len(leg_dests)} destinations tagged.")

        legacy_conn.close()
        local_conn.close()
        print("=== Shadow Sync Complete ===")

    except Exception as e:
        print(f"[Shadow-Sync Error] {e}")

if __name__ == "__main__":
    sync_legacy_metadata()
