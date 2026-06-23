#!/usr/bin/env python3
import os
import sys
import argparse
import requests
import pymysql
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
