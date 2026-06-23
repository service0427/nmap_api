import os
import sys
import hashlib
import json
import pymysql
import importlib
import argparse
import re
from datetime import datetime, date, timedelta

# 경로 설정
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_DIR)

from core.config import Config
from core.scraper import NaverPlaceScraper
from core.utils import get_kst_now

# 공통 설정 및 인스턴스
HASH_DIR = os.path.join(PROJECT_DIR, "data/hashes")
if not os.path.exists(HASH_DIR):
    os.makedirs(HASH_DIR)

scraper_instance = NaverPlaceScraper()

def get_hash(data):
    return hashlib.md5(str(data).encode()).hexdigest()

def log_sync_summary(cursor, site_id, fetched, inserted, updated, deleted, error=None):
    kst_now = get_kst_now()
    cursor.execute("""
        INSERT INTO sync_log_summary (site_id, sync_time, total_fetched, inserted_cnt, updated_cnt, deleted_cnt, error_msg)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (site_id, kst_now, fetched, inserted, updated, deleted, error))
    return cursor.lastrowid

def log_sync_detail(cursor, summary_id, site_id, sid, action, old_data=None, new_data=None):
    cursor.execute("""
        INSERT INTO sync_log_detail (summary_id, site_id, sid, action_type, old_data, new_data)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (summary_id, site_id, sid, action, json.dumps(old_data) if old_data else None, json.dumps(new_data) if new_data else None))

def ensure_place_info(cursor, dest_id, source_places_cache=None, force_update=False):
    cursor.execute("SELECT dest_id, original_address, updated_at FROM places WHERE dest_id = %s", (dest_id,))
    row = cursor.fetchone()
    
    # 1. 정보가 아예 없거나, original_address가 없는 경우 (최초 수집/마이그레이션)
    # 2. 실패가 많아서 강제 업데이트가 필요한 경우 (단, 네이버 차단 방지를 위해 최소 1시간 간격 유지)
    should_fetch = False
    if not row or row.get('original_address') is None:
        should_fetch = True
    elif force_update:
        last_upd = row.get('updated_at')
        if not last_upd or last_upd < get_kst_now() - timedelta(hours=1):
            should_fetch = True

    if should_fetch:
        # 강제 업데이트가 아닐 때만 소스 캐시 활용 (원본 FSD 정보)
        if source_places_cache and dest_id in source_places_cache and source_places_cache[dest_id].get('name') and not force_update:
            sp = source_places_cache[dest_id]
            cursor.execute("""
                INSERT INTO places (dest_id, name, address, lat, lng)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE name=VALUES(name), address=VALUES(address), lat=VALUES(lat), lng=VALUES(lng)
            """, (sp['dest_id'], sp['name'], sp['address'], sp['lat'], sp['lng']))
            return True

        # 정밀 재수집 (POI -> instantSearchV2)
        info = scraper_instance.fetch_place_info(dest_id)
        if info and "error" not in info:
            name = info['name']
            is_opt = 1 if re.search(r'누수|청소|하수구|변기|이사', name) else 0
            
            cursor.execute("""
                INSERT INTO places (dest_id, name, address, original_address, lat, lng, is_optimizer)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    name=VALUES(name), 
                    address=VALUES(address), 
                    original_address=VALUES(original_address),
                    lat=VALUES(lat), 
                    lng=VALUES(lng), 
                    is_optimizer=VALUES(is_optimizer),
                    updated_at=VALUES(updated_at)
            """, (info['id'], name, info['address'], info.get('original_address'), info['lat'], info['lng'], is_opt))
            return True
        else:
            cursor.execute("""
                INSERT INTO places (dest_id, name, check_status)
                VALUES (%s, %s, 'FAIL')
                ON DUPLICATE KEY UPDATE check_status='FAIL'
            """, (dest_id, f"FAILED_SCRAPE_{dest_id}"))
            return False
    return True

def fetch_source_destinations_cache():
    try:
        conf = Config.get_source_fsd_config()
        if not conf.get('host'): return {}
        conn = pymysql.connect(**conf)
        with conn.cursor() as cursor:
            cursor.execute("SELECT dest_id, name, address, lat, lng FROM destinations")
            rows = cursor.fetchall()
        conn.close()
        return {str(r['dest_id']): r for r in rows}
    except:
        return {}

def process_sync(site_id, standardized_data, source_places_cache=None, dry_run=False):
    if dry_run:
        print(f"\n--- [DRY-RUN] Data for {site_id} ({len(standardized_data)} items) ---")
        for item in standardized_data[:3]: print(f"  Sample: {item}")
        return

    print(f"--- [Sync] Processing {site_id} ---")
    
    conn = pymysql.connect(**Config.get_db_config(), autocommit=True)
    try:
        with conn.cursor() as cursor:
            standardized_data.sort(key=lambda x: x['sid'])
            new_hash = hashlib.md5(json.dumps(standardized_data, default=str).encode()).hexdigest()
            
            hash_file = os.path.join(HASH_DIR, f"sync_hash_{site_id}.txt")
            if os.path.exists(hash_file):
                with open(hash_file, "r") as f:
                    if f.read().strip() == new_hash:
                        cursor.execute("SELECT COUNT(*) as cnt FROM raw_slots WHERE site_id = %s", (site_id,))
                        if cursor.fetchone()['cnt'] > 0:
                            print(f"[{site_id}] No changes detected via hash.")
                            return

            cursor.execute("SELECT sid, dest_id, work_count, start_date, end_date, config_hash, status FROM raw_slots WHERE site_id = %s", (site_id,))
            current_state = {row['sid']: row for row in cursor.fetchall()}
            
            inserted, updated, deleted = 0, 0, 0
            summary_id = log_sync_summary(cursor, site_id, len(standardized_data), 0, 0, 0)
            
            new_sid_list = set()
            for item in standardized_data:
                sid = item['sid']
                new_sid_list.add(sid)
                
                # 실패가 2회 이상이면 정보가 틀렸을 가능성이 있으므로 강제 재수집 시도
                fail_cnt = item.get('fail_count', 0)
                is_high_failure = True if fail_cnt >= 2 else False
                ensure_place_info(cursor, item['dest_id'], source_places_cache, force_update=is_high_failure)
                
                if fail_cnt >= 2:
                    cursor.execute("""
                        UPDATE places 
                        SET is_optimizer = 1 
                        WHERE dest_id = %s 
                          AND (check_status IS NULL OR check_status != 'VERIFIED' OR last_optimized_at < %s - INTERVAL 6 HOUR)
                    """, (item['dest_id'], get_kst_now()))
                
                if 'success_count' in item:
                    cursor.execute("""
                        INSERT INTO daily_progress (work_date, site_id, dest_id, success_cnt, fail_cnt, alloc_fail_cnt, last_dist_m)
                        VALUES (%s, %s, %s, %s, 0, 0, 800)
                        ON DUPLICATE KEY UPDATE success_cnt = GREATEST(success_cnt, %s)
                    """, (get_kst_date(), site_id, item['dest_id'], item['success_count'], item['success_count']))
                
                record_str = f"{site_id}_{sid}_{item['dest_id']}_{item['work_count']}_{item['start_date']}_{item['end_date']}"
                config_hash = hashlib.md5(record_str.encode()).hexdigest()
                
                if sid not in current_state:
                    cursor.execute("""
                        INSERT INTO raw_slots (site_id, sid, dest_id, work_count, start_date, end_date, config_hash, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (site_id, sid, item['dest_id'], item['work_count'], item['start_date'], item['end_date'], config_hash, get_kst_now()))
                    log_sync_detail(cursor, summary_id, site_id, sid, 'INSERT', new_data=item)
                    inserted += 1
                else:
                    old = current_state[sid]
                    if old['config_hash'] != config_hash or old['status'] != 'on':
                        cursor.execute("""
                            UPDATE raw_slots SET dest_id=%s, work_count=%s, start_date=%s, end_date=%s, config_hash=%s, status='on', updated_at=%s
                            WHERE site_id=%s AND sid=%s
                        """, (item['dest_id'], item['work_count'], item['start_date'], item['end_date'], config_hash, get_kst_now(), site_id, sid))
                        updated += 1
            
            for sid in current_state:
                if sid not in new_sid_list:
                    cursor.execute("UPDATE raw_slots SET status='off', updated_at=%s WHERE site_id=%s AND sid=%s", (get_kst_now(), site_id, sid))
                    deleted += 1
            
            cursor.execute("UPDATE sync_log_summary SET inserted_cnt=%s, updated_cnt=%s, deleted_cnt=%s WHERE id=%s", (inserted, updated, deleted, summary_id))
            with open(hash_file, "w") as f: f.write(new_hash)
            print(f"[{site_id}] Completed: Ins={inserted}, Upd={updated}, Del={deleted}")
            
    except Exception as e:
        print(f"[{site_id}] Sync Error: {e}")
    finally:
        conn.close()

def run_all_syncs(dry_run=False):
    source_places_cache = fetch_source_destinations_cache()
    modules_dir = os.path.join(os.path.dirname(__file__), "sync_modules")
    if not os.path.exists(modules_dir): return
    for filename in os.listdir(modules_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = filename[:-3]
            try:
                module = importlib.import_module(f"core.sync_modules.{module_name}")
                if hasattr(module, "fetch_data"):
                    data = module.fetch_data()
                    if data is not None: process_sync(module_name.upper(), data, source_places_cache, dry_run=dry_run)
            except Exception as e: print(f"[{module_name.upper()}] ERROR: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nmap API Sync Engine")
    parser.add_argument("--dry-run", action="store_true", help="Print collected data without updating database")
    args = parser.parse_args()
    run_all_syncs(dry_run=args.dry_run)
