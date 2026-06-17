import os
import sys

# Path adjustment for standalone execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from datetime import datetime, date, timedelta
from core.config import Config
from core.utils import get_kst_now, get_kst_date

# Config
DB_CONFIG = Config.get_fresh_db_config() if hasattr(Config, 'get_fresh_db_config') else Config.get_db_config()

def aggregate_daily_quota():
    """
    Initializes/Verifies today's and tomorrow's records in daily_progress.
    Inherits last_dist_m from previous successful day to enable long-term expansion.
    """
    kst_now = get_kst_now()
    kst_date = get_kst_date()
    print(f"--- Running Daily Aggregator: {kst_now} ---")
    
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            # We initialize for both Today and Tomorrow to avoid the midnight gap
            days_to_sync = [kst_date, kst_date + timedelta(days=1)]
            
            for target_date in days_to_sync:
                d_str = target_date.isoformat()
                
                # Logic: Insert new record, or update if exists.
                # If inserting new: Try to fetch the most recent last_dist_m for this place.
                sql = """
                    INSERT INTO daily_progress (work_date, site_id, dest_id, success_cnt, fail_cnt, last_dist_m, updated_at)
                    SELECT 
                        %s, 
                        s.site_id, 
                        s.dest_id, 
                        0, 0,
                        IFNULL(
                            (SELECT dp2.last_dist_m FROM daily_progress dp2 
                             WHERE dp2.dest_id = s.dest_id 
                               AND dp2.work_date < %s 
                               AND dp2.success_cnt > 0
                             ORDER BY dp2.work_date DESC LIMIT 1), 
                            800
                        ),
                        %s
                    FROM raw_slots s
                    WHERE s.status = 'on'
                      AND %s BETWEEN s.start_date AND s.end_date
                    GROUP BY s.site_id, s.dest_id
                    ON DUPLICATE KEY UPDATE updated_at = %s;
                """
                # Parameters: target_date (for work_date), target_date (for subquery limit), kst_now (updated_at), target_date (for raw_slots filter), kst_now (on duplicate update)
                cursor.execute(sql, (d_str, d_str, kst_now, d_str, kst_now))
                print(f"  [{d_str}] Slots verified: {cursor.rowcount}")
            
        conn.commit()
    except Exception as e:
        print(f"Error in aggregator: {e}")
    finally:
        if 'conn' in locals(): conn.close()

def sync_workload_to_legacy():
    """
    Syncs local daily_progress (site_id = 'FSD') success_cnt and fail_cnt 
    back to the legacy FSD daily_tasks table for today and tomorrow.
    """
    kst_now = get_kst_now()
    kst_date = get_kst_date()
    print(f"--- Syncing Workload to Legacy (FSD): {kst_now} ---")
    
    legacy_conf = Config.get_source_fsd_config()
    if not legacy_conf.get('host'):
        print("  [FSD] Skip: Legacy DB configuration missing.")
        return
        
    try:
        local_conn = pymysql.connect(**DB_CONFIG)
        legacy_conn = pymysql.connect(**legacy_conf, autocommit=True)
        
        days_to_sync = [kst_date, kst_date + timedelta(days=1)]
        
        with local_conn.cursor() as loc_cur, legacy_conn.cursor() as leg_cur:
            for target_date in days_to_sync:
                d_str = target_date.isoformat()
                
                # Fetch local daily progress for FSD
                loc_cur.execute("""
                    SELECT dest_id, success_cnt, fail_cnt 
                    FROM daily_progress 
                    WHERE work_date = %s AND site_id = 'FSD'
                """, (d_str,))
                progress_rows = loc_cur.fetchall()
                
                if not progress_rows:
                    print(f"  [{d_str}] No local progress records to sync.")
                    continue
                
                # Upsert to FSD daily_tasks
                synced_cnt = 0
                for row in progress_rows:
                    sql = """
                        INSERT INTO daily_tasks (dest_id, work_date, success_count, fail_count)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE 
                            success_count = VALUES(success_count),
                            fail_count = VALUES(fail_count)
                    """
                    leg_cur.execute(sql, (row['dest_id'], d_str, row['success_cnt'], row['fail_cnt']))
                    synced_cnt += 1
                
                print(f"  [{d_str}] Synced {synced_cnt} records to FSD daily_tasks.")
                
        local_conn.close()
        legacy_conn.close()
    except Exception as e:
        print(f"Error in sync_workload_to_legacy: {e}")

if __name__ == "__main__":
    aggregate_daily_quota()
    sync_workload_to_legacy()
