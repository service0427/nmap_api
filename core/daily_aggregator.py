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
            # Daily Reset of Optimizer targets: Run once a day during the 3:00 AM hour KST
            if kst_now.hour == 3:
                project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                cleanup_run_file = os.path.join(project_dir, "data/hashes/cleanup_last_run.txt")
                already_run = False
                if os.path.exists(cleanup_run_file):
                    with open(cleanup_run_file, "r") as f:
                        if f.read().strip() == kst_date.isoformat():
                            already_run = True
                            
                if not already_run:
                    print("  Running Daily Optimizer Reset...")
                    try:
                        cursor.execute("""
                            UPDATE places 
                            SET is_optimizer = 0,
                                dist_min_m = 1000,
                                dist_max_m = 3000,
                                check_status = 'NORMAL'
                            WHERE is_optimizer = 1 OR check_status = 'FAIL'
                        """)
                        print(f"    Reset {cursor.rowcount} places optimizer status and restored 1km~3km distances for the new day.")
                    except Exception as ex_reset:
                        print(f"    Error resetting daily optimizer places: {ex_reset}")
                    
                    try:
                        os.makedirs(os.path.dirname(cleanup_run_file), exist_ok=True)
                        with open(cleanup_run_file, "w") as f:
                            f.write(kst_date.isoformat())
                    except Exception as ex_file:
                        print(f"    Error writing cleanup_last_run file: {ex_file}")

            # We initialize for both Today and Tomorrow to avoid the midnight gap
            days_to_sync = [kst_date, kst_date + timedelta(days=1)]
            
            for target_date in days_to_sync:
                d_str = target_date.isoformat()
                
                # Logic: Insert new record, or update if exists.
                # If inserting new: Try to fetch the most recent last_dist_m for this place.
                sql = """
                    INSERT INTO daily_progress (work_date, site_id, dest_id, total_target, success_cnt, fail_cnt, last_dist_m, updated_at)
                    SELECT 
                        %s, 
                        s.site_id, 
                        s.dest_id, 
                        SUM(s.work_count),
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
                      AND s.is_deleted = 0
                      AND %s BETWEEN s.start_date AND s.end_date
                    GROUP BY s.site_id, s.dest_id
                    ON DUPLICATE KEY UPDATE 
                        total_target = VALUES(total_target),
                        updated_at = %s;
                """
                # Parameters: target_date (for work_date), target_date (for subquery limit), kst_now (updated_at), target_date (for raw_slots filter), kst_now (on duplicate update)
                cursor.execute(sql, (d_str, d_str, kst_now, d_str, kst_now))
                print(f"  [{d_str}] Slots verified: {cursor.rowcount}")
                
                # Aggregate from raw_slots_tmp for ssolup and ghost2026
                tmp_sql = """
                    INSERT INTO daily_progress (work_date, site_id, dest_id, total_target, success_cnt, fail_cnt, last_dist_m, updated_at)
                    SELECT 
                        %s, 
                        s.site, 
                        s.dest_id, 
                        SUM(s.work_count),
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
                    FROM raw_slots_tmp s
                    WHERE s.work_date = %s
                      AND s.dest_id IS NOT NULL AND s.dest_id != ''
                    GROUP BY s.site, s.dest_id
                    ON DUPLICATE KEY UPDATE 
                        total_target = VALUES(total_target),
                        updated_at = %s;
                """
                cursor.execute(tmp_sql, (d_str, d_str, kst_now, d_str, kst_now))
                print(f"  [{d_str}] Tmp slots verified: {cursor.rowcount}")
            
        conn.commit()
    except Exception as e:
        print(f"Error in aggregator: {e}")
    finally:
        if 'conn' in locals(): conn.close()

def sync_workload_to_legacy():
    """
    Syncs local daily_progress (site_id = 'FSD') success_cnt and fail_cnt 
    back to the legacy FSD daily_tasks table.
    Disabled on nmap_api_v1 (100% independent server)
    """
    print("  [FSD] Legacy workload sync disabled on nmap_api_v1.")
    return

def calculate_7day_stats():
    """
    1) 과거 7일치(어제부터 과거 7일간)의 실제 수행 통계를 daily_progress로부터 daily_stats에 갱신.
    2) 오늘 포함 미래 7일치(D-0 ~ D+6)의 예상 슬롯 목표량을 raw_slots로부터 실시간 집계하여 daily_stats에 캐싱.
    """
    kst_now = get_kst_now()
    kst_date = get_kst_date()
    print(f"--- Calculating Rolling Stats (Past & Future): {kst_now} ---")
    
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            # 1. 과거 7일치 집계 (어제 D-1 ~ 7일전 D-7)
            past_sql = """
                INSERT INTO daily_stats (work_date, total_target, success_cnt, fail_cnt, updated_at)
                SELECT 
                    work_date,
                    SUM(total_target) as total_target,
                    SUM(success_cnt) as success_cnt,
                    SUM(fail_cnt) as fail_cnt,
                    %s
                FROM daily_progress
                WHERE work_date BETWEEN DATE_SUB(%s, INTERVAL 7 DAY) AND DATE_SUB(%s, INTERVAL 1 DAY)
                GROUP BY work_date
                ON DUPLICATE KEY UPDATE 
                    total_target = VALUES(total_target),
                    success_cnt = VALUES(success_cnt),
                    fail_cnt = VALUES(fail_cnt),
                    updated_at = VALUES(updated_at);
            """
            cursor.execute(past_sql, (kst_now, kst_date, kst_date))
            
            # 2. 오늘 포함 미래 7일치 집계 (오늘 D-0 ~ 6일후 D+6)
            for i in range(7):
                target_date = kst_date + timedelta(days=i)
                t_str = target_date.isoformat()
                
                # 해당 미래 날짜 기준 유효 슬롯들의 목표량 합산
                future_sql = """
                    SELECT (
                        SELECT IFNULL(SUM(s.work_count), 0)
                        FROM raw_slots s
                        WHERE s.status = 'on'
                          AND s.is_deleted = 0
                          AND %s BETWEEN s.start_date AND s.end_date
                    ) + (
                        SELECT IFNULL(SUM(st.work_count), 0)
                        FROM raw_slots_tmp st
                        WHERE st.work_date = %s
                          AND st.dest_id IS NOT NULL AND st.dest_id != ''
                    ) as total
                """
                cursor.execute(future_sql, (t_str, t_str))
                target_sum = cursor.fetchone()['total'] or 0
                
                # 오늘인 경우(D-0), 당일 실시간 성공/실패 수치도 함께 반영해 업서트
                if i == 0:
                    # places 상태별 카운트 집계
                    cursor.execute("""
                        SELECT 
                            SUM(CASE WHEN check_status = 'PENDING' THEN 1 ELSE 0 END) as p_cnt,
                            SUM(CASE WHEN check_status = 'VERIFIED' THEN 1 ELSE 0 END) as v_cnt,
                            SUM(CASE WHEN check_status = 'FAIL' THEN 1 ELSE 0 END) as f_cnt
                        FROM places
                    """)
                    places_stats = cursor.fetchone()
                    pending_places = places_stats['p_cnt'] or 0
                    verified_places = places_stats['v_cnt'] or 0
                    fail_places = places_stats['f_cnt'] or 0

                    cursor.execute("""
                        SELECT SUM(success_cnt) as s, SUM(fail_cnt) as f 
                        FROM daily_progress 
                        WHERE work_date = %s
                    """, (t_str,))
                    prog = cursor.fetchone()
                    s_cnt = prog['s'] or 0
                    f_cnt = prog['f'] or 0
                    
                    cursor.execute("""
                        INSERT INTO daily_stats (work_date, total_target, success_cnt, fail_cnt, pending_places, verified_places, fail_places, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE 
                            total_target = VALUES(total_target),
                            success_cnt = VALUES(success_cnt),
                            fail_cnt = VALUES(fail_cnt),
                            pending_places = VALUES(pending_places),
                            verified_places = VALUES(verified_places),
                            fail_places = VALUES(fail_places),
                            updated_at = VALUES(updated_at);
                    """, (t_str, target_sum, s_cnt, f_cnt, pending_places, verified_places, fail_places, kst_now))
                else:
                    # 미래 날짜들은 성공/실패가 0
                    cursor.execute("""
                        INSERT INTO daily_stats (work_date, total_target, success_cnt, fail_cnt, updated_at)
                        VALUES (%s, %s, 0, 0, %s)
                        ON DUPLICATE KEY UPDATE 
                            total_target = VALUES(total_target),
                            updated_at = VALUES(updated_at);
                    """, (t_str, target_sum, kst_now))
                    
            print(f"  Rolling stats (past & future) updated successfully.")
        conn.commit()
    except Exception as e:
        print(f"Error in calculate_7day_stats: {e}")
    finally:
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    aggregate_daily_quota()
    sync_workload_to_legacy()
    calculate_7day_stats()
