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

if __name__ == "__main__":
    aggregate_daily_quota()
