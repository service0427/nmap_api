#!/usr/bin/env python3
import os
import sys
import argparse
import requests
import pymysql
import re
import json
import hashlib
import time
from datetime import datetime

# Adjust path for standalone execution
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_DIR)

from core.config import Config
from core.utils import get_kst_now, get_kst_date

def get_default_work_amount(site_db_name):
    """Fetches the default_work_amount setting from the site's local database."""
    db_config = Config.get_db_config()
    # Clone the config and change the database name
    site_db_config = db_config.copy()
    # If the user is 'nmap', it might not have access to ssolup/ghost2026.
    # But since we saw the 'slot' user can access it, let's try using the credentials from .env first,
    # or fallback to slot/Tech1324 if needed.
    site_db_config['database'] = site_db_name
    
    try:
        conn = pymysql.connect(**site_db_config)
        with conn.cursor() as cursor:
            cursor.execute("SELECT value FROM system_settings WHERE `key` = 'default_work_amount'")
            row = cursor.fetchone()
            if row and row.get('value'):
                return int(row['value'])
    except Exception as e:
        print(f"[{site_db_name.upper()}] Failed to fetch default_work_amount from DB ({e}). Falling back to 5.")
    return 5

def fetch_all_slots(api_url, target_date_str):
    """Fetches all slots page by page from the work-details API."""
    all_items = []
    page = 1
    limit = 1000
    
    while True:
        url = f"{api_url}?date={target_date_str}&page={page}&limit={limit}"
        print(f"  Fetching page {page} from {url}...")
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"  HTTP Error: {resp.status_code}")
                break
                
            data = resp.json()
            items = data.get('items', [])
            if not items:
                break
                
            all_items.extend(items)
            print(f"  Page {page}: Got {len(items)} items. Total collected so far: {len(all_items)}")
            
            # If we fetched fewer items than limit or reached total, stop
            total = data.get('total', 0)
            if len(all_items) >= total or len(items) < limit:
                break
                
            page += 1
        except Exception as e:
            print(f"  Request exception: {e}")
            break
            
    return all_items

def sync_rudolph_work(cursor, target_date_str):
    import re
    import hashlib
    print("\nProcessing site: [RUDOLPH]")
    
    hash_dir = os.path.join(PROJECT_DIR, "data/hashes")
    hash_file = os.path.join(hash_dir, f"sync_hash_work_details_rudolph.txt")
    
    # Helper to extract place_id
    def extract_place_id(url):
        if not url:
            return None
        url = str(url).strip()
        match = re.search(r'/(?:place|restaurant|hospital|hairshop|nail|accommodation|stay|hotel|camping|resort|guestHouse|motel|pension|spa|studio|gym|academy|store)/(\d+)', url)
        if match:
            return match.group(1)
        match = re.search(r'/([a-zA-Z]+)/(\d+)', url)
        if match:
            return match.group(2)
        match = re.search(r'/(\d+)', url)
        if match:
            return match.group(1)
        return None

    # 1. Login to Rudolph
    login_url = "http://rudolph-slot.club/login"
    login_payload = {
        "nickname": "rudolph",
        "password": "rltjrWkd"
    }
    
    session = requests.Session()
    try:
        resp = session.post(login_url, data=login_payload, allow_redirects=False, timeout=15)
        if resp.status_code != 302:
            print(f"  [RUDOLPH] Login failed, status code: {resp.status_code}")
            return
    except Exception as e:
        print(f"  [RUDOLPH] Login request failed: {e}")
        return
        
    # 2. Fetch slots page by page (500 items per page with full payload)
    data_url = "http://rudolph-slot.club/accounts/slots/all"
    data_headers = {
        "content-type": "application/json",
        "x-requested-with": "XMLHttpRequest",
        "Referer": "http://rudolph-slot.club/slot_list",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # We send full columns mapping to enable the server to return 500 items per request
    payload_columns = [
        {"data": None, "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "id", "name": "id", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": None, "name": "", "searchable": True, "orderable": False, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "start_date", "name": "start_date", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "end_date", "name": "end_date", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "end_date", "name": "remaining_days", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "duration", "name": "duration", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "advertiser", "name": "advertiser", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "platform.name", "name": "platform_name", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "rank", "name": "rank", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "inflow_platform", "name": "inflow_platform", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "keyword", "name": "keyword", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "subkeyword", "name": "subkeyword", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "brand_store_name", "name": "brand_store_name", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "product_name", "name": "product_name", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "url", "name": "url", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "compare_url", "name": "compare_url", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "extra_field_2", "name": "extra_field_2", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "price", "name": "price", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "image_url", "name": "image_url", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "public_memo", "name": "public_memo", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "created_at", "name": "created_at", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "start_date", "name": "start_date_excel", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}},
        {"data": "end_date", "name": "end_date_excel", "searchable": True, "orderable": True, "search": {"value": "", "regex": False, "fixed": []}}
    ]

    payload = {
        "draw": 1,
        "columns": payload_columns,
        "order": [{"column": 1, "dir": "desc", "name": "id"}],
        "start": 0,
        "length": -1,
        "slot_type": "6",
        "pageLength": -1,
        "_ts": int(time.time() * 1000),
        "sort_field": "id",
        "sort_dir": "desc"
    }
    
    print(f"  Fetching all Rudolph slots in a single query (length: -1)...")
    try:
        resp = session.post(data_url, headers=data_headers, json=payload, timeout=25)
        if resp.status_code != 200:
            print(f"  [RUDOLPH] HTTP Error {resp.status_code} fetching slots")
            return
        result = resp.json()
    except Exception as e:
        print(f"  [RUDOLPH] Request failed: {e}")
        return
        
    all_slots = result.get("data", [])
    print(f"  [RUDOLPH] Fetched total {len(all_slots)} slot records.")
    
    # 3. Filter active slots for target_date_str and parse place IDs
    active_slots = []
    seen_ids = set()
    for item in all_slots:
        sid = item.get("id")
        if sid is None or sid in seen_ids:
            continue
        url = str(item.get("url") or "").strip()
        dest_id = extract_place_id(url)
        if not dest_id:
            continue
        start_date = item.get("start_date")
        end_date = item.get("end_date")
        if start_date and end_date and start_date <= target_date_str <= end_date:
            active_slots.append(item)
            seen_ids.add(sid)
            
    print(f"  [RUDOLPH] Found {len(active_slots)} active slots for date {target_date_str}.")
    
    if not active_slots:
        print("  [RUDOLPH] No active slots to insert.")
        return
        
    # 4. Check hash of the active slots to skip if no changes
    # Sort by slot ID to make hash deterministic
    active_slots.sort(key=lambda x: int(x.get("id", 0)))
    hash_data = [(str(x.get("id")), extract_place_id(x.get("url")), 5) for x in active_slots]
    new_hash = hashlib.md5(json.dumps(hash_data).encode()).hexdigest()
    
    if os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            saved_content = f.read().strip()
        if saved_content == f"{target_date_str}:{new_hash}":
            cursor.execute("SELECT COUNT(*) as cnt FROM raw_slots_tmp WHERE site = 'RUDOLPH' AND work_date = %s", (target_date_str,))
            cnt_row = cursor.fetchone()
            if cnt_row and cnt_row.get('cnt', 0) > 0:
                print(f"  [RUDOLPH] No changes detected via hash ({new_hash}) for date {target_date_str}. Skipping sync.")
                return

    # 5. Clear existing Rudolph records for this date
    cursor.execute("""
        DELETE FROM raw_slots_tmp 
        WHERE site = 'RUDOLPH' AND work_date = %s
    """, (target_date_str,))
    deleted_rows = cursor.rowcount
    print(f"  [RUDOLPH] Cleared {deleted_rows} existing records for {target_date_str}.")
    
    # 6. Insert slot details individually
    inserted_cnt = 0
    kst_now = get_kst_now()
    for item in active_slots:
        sid = str(item.get("id"))
        url = str(item.get("url"))
        dest_id = extract_place_id(url)
        work_count = 5 # Rudolph slot work_amount is 5
        
        cursor.execute("""
            INSERT INTO raw_slots_tmp (site, sid, dest_id, work_count, work_date, created_at)
            VALUES ('RUDOLPH', %s, %s, %s, %s, %s)
        """, (sid, dest_id, work_count, target_date_str, kst_now))
        inserted_cnt += 1
        
    print(f"  [RUDOLPH] Successfully inserted {inserted_cnt} slots (total workload: {inserted_cnt * 5}).")
    
    # 7. Save hash
    with open(hash_file, "w") as f:
        f.write(f"{target_date_str}:{new_hash}")
    print(f"  [RUDOLPH] Saved sync hash: {new_hash}")

def sync_luf_work(cursor, target_date_str):
    import hashlib
    print("\nProcessing site: [LUF]")
    
    hash_dir = os.path.join(PROJECT_DIR, "data/hashes")
    hash_file = os.path.join(hash_dir, f"sync_hash_work_details_luf.txt")
    
    url = f"https://lufons.link/api/external/work?date={target_date_str}"
    print(f"  Fetching LUF data from: {url}...")
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  [LUF] HTTP Error: {resp.status_code}")
            return
        data_list = resp.json()
    except Exception as e:
        print(f"  [LUF] Request exception: {e}")
        return
        
    if not isinstance(data_list, list):
        print(f"  [LUF] Invalid API response format: expected list")
        return
        
    if len(data_list) < 500:
        print(f"  [LUF] Sync aborted: API returned only {len(data_list)} items (expected >= 500).")
        return
        
    # Calculate hash of the content
    new_hash = hashlib.md5(resp.content).hexdigest()
    
    # Check if hash matches
    if os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            saved_content = f.read().strip()
        if saved_content == f"{target_date_str}:{new_hash}":
            # Double check if raw_slots_tmp has records
            cursor.execute("SELECT COUNT(*) as cnt FROM raw_slots_tmp WHERE site = 'LUF' AND work_date = %s", (target_date_str,))
            cnt_row = cursor.fetchone()
            if cnt_row and cnt_row.get('cnt', 0) > 0:
                print(f"  [LUF] No changes detected via hash ({new_hash}) for date {target_date_str}. Skipping sync.")
                return

    # Clear existing LUF records for this date
    cursor.execute("""
        DELETE FROM raw_slots_tmp 
        WHERE site = 'LUF' AND work_date = %s
    """, (target_date_str,))
    deleted_rows = cursor.rowcount
    print(f"  [LUF] Cleared {deleted_rows} existing records for {target_date_str}.")
    
    # Insert slots
    inserted_cnt = 0
    kst_now = get_kst_now()
    for index, item in enumerate(data_list):
        code = str(item.get('code'))
        if not code or code == 'None':
            continue
        sid = str(index + 1)
        work_count = int(item.get('work_amount', 0))
        
        cursor.execute("""
            INSERT INTO raw_slots_tmp (site, sid, dest_id, work_count, work_date, created_at)
            VALUES ('LUF', %s, %s, %s, %s, %s)
        """, (sid, code, work_count, target_date_str, kst_now))
        inserted_cnt += 1
        
    print(f"  [LUF] Successfully inserted {inserted_cnt} slots.")
    
    # Save the new hash
    with open(hash_file, "w") as f:
        f.write(f"{target_date_str}:{new_hash}")
    print(f"  [LUF] Saved sync hash: {new_hash}")

def sync_work_details(target_date_str):
    print(f"=== Syncing work-details for date: {target_date_str} ===")
    
    sites = {
        'ssolup': {
            'db_name': 'ssolup',
            'api_url': 'https://ssolup.com/api/external/work-details'
        },
        'ghost2026': {
            'db_name': 'ghost2026',
            'api_url': 'https://ghost2026.com/api/external/work-details'
        }
    }
    
    # Establish connection to nmap_api_v1
    nmap_db_config = Config.get_db_config()
    conn = pymysql.connect(**nmap_db_config, autocommit=False)
    
    # Define Hash Dir
    hash_dir = os.path.join(PROJECT_DIR, "data/hashes")
    if not os.path.exists(hash_dir):
        os.makedirs(hash_dir)
        
    try:
        with conn.cursor() as cursor:
            for site_name, info in sites.items():
                print(f"\nProcessing site: [{site_name}]")
                default_work_amount = get_default_work_amount(info['db_name'])
                print(f"  [{site_name}] Using default work amount: {default_work_amount}")
                
                # Fetch first page to inspect the hash and total
                url = f"{info['api_url']}?date={target_date_str}&page=1&limit=1000"
                print(f"  Fetching page 1 from {url}...")
                try:
                    resp = requests.get(url, timeout=15)
                    if resp.status_code != 200:
                        print(f"  HTTP Error: {resp.status_code}")
                        continue
                    data = resp.json()
                except Exception as e:
                    print(f"  Request exception: {e}")
                    continue
                
                items = data.get('items', [])
                total = data.get('total', 0)
                new_hash = data.get('hash')
                
                if new_hash:
                    hash_file = os.path.join(hash_dir, f"sync_hash_work_details_{site_name}.txt")
                    # Check if date and hash match
                    if os.path.exists(hash_file):
                        with open(hash_file, "r") as f:
                            saved_content = f.read().strip()
                        if saved_content == f"{target_date_str}:{new_hash}":
                            # Double check if raw_slots_tmp has records
                            cursor.execute("SELECT COUNT(*) as cnt FROM raw_slots_tmp WHERE site = %s AND work_date = %s", (site_name, target_date_str))
                            cnt_row = cursor.fetchone()
                            if cnt_row and cnt_row.get('cnt', 0) > 0:
                                print(f"  [{site_name}] No changes detected via hash ({new_hash}) for date {target_date_str}. Skipping sync.")
                                continue
                
                # If hash didn't match (or wasn't present), proceed with full sync
                slots = []
                slots.extend(items)
                
                # Fetch remaining pages if any
                limit = 1000
                page = 2
                while len(slots) < total and len(items) >= limit:
                    next_url = f"{info['api_url']}?date={target_date_str}&page={page}&limit={limit}"
                    print(f"  Fetching page {page} from {next_url}...")
                    try:
                        resp = requests.get(next_url, timeout=15)
                        if resp.status_code != 200:
                            print(f"  HTTP Error: {resp.status_code}")
                            break
                        page_data = resp.json()
                        items = page_data.get('items', [])
                        if not items:
                            break
                        slots.extend(items)
                        print(f"  Page {page}: Got {len(items)} items. Total collected so far: {len(slots)}")
                        page += 1
                    except Exception as e:
                        print(f"  Request exception: {e}")
                        break
                
                print(f"  [{site_name}] Fetched total {len(slots)} slots.")
                
                # Check for incomplete fetch to ensure atomicity
                if total > 0 and len(slots) < total:
                    raise RuntimeError(f"Sync failed for [{site_name}]: fetched {len(slots)} items but expected total {total}. Aborting transaction to prevent incomplete data.")
                
                # Clear existing records for this site and date to prevent duplicates
                cursor.execute("""
                    DELETE FROM raw_slots_tmp 
                    WHERE site = %s AND work_date = %s
                """, (site_name, target_date_str))
                deleted_rows = cursor.rowcount
                print(f"  [{site_name}] Cleared {deleted_rows} existing records for {target_date_str}.")
                
                if not slots:
                    print(f"  [{site_name}] No slots to insert.")
                    continue
                
                # Insert the slots
                inserted_cnt = 0
                kst_now = get_kst_now()
                
                for item in slots:
                    sid = str(item.get('slot_id') or item.get('sid'))
                    dest_id = str(item.get('code'))
                    
                    cursor.execute("""
                        INSERT INTO raw_slots_tmp (site, sid, dest_id, work_count, work_date, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (site_name, sid, dest_id, default_work_amount, target_date_str, kst_now))
                    inserted_cnt += 1
                
                print(f"  [{site_name}] Successfully inserted {inserted_cnt} slots.")
                
                # Save the new hash
                if new_hash:
                    with open(hash_file, "w") as f:
                        f.write(f"{target_date_str}:{new_hash}")
                    print(f"  [{site_name}] Saved sync hash: {new_hash}")
            # Sync LUF to raw_slots_tmp
            sync_luf_work(cursor, target_date_str)
            
            # Sync RUDOLPH to raw_slots_tmp
            sync_rudolph_work(cursor, target_date_str)
            
            # Commit the transaction
            conn.commit()
            print("\n=== Sync completed successfully and committed. ===")
            
    except Exception as e:
        conn.rollback()
        print(f"\nError during sync execution: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync detailed slot workloads into raw_slots_tmp")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD), defaults to today")
    args = parser.parse_args()
    
    if args.date:
        target_date_str = args.date
    else:
        target_date_str = get_kst_date().isoformat()
        
    sync_work_details(target_date_str)
