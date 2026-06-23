import requests
import json
import time
import os
import sys
import argparse
import re

# Adjust path for importing project core modules if run standalone
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
if project_dir not in sys.path:
    sys.path.append(project_dir)

try:
    from core.config import Config
    from core.utils import get_kst_now, get_kst_date
    HAS_CORE = True
except ImportError:
    HAS_CORE = False

def extract_place_id(url):
    """
    Extracts Naver Place ID (digits) from various Naver Place URL formats.
    """
    if not url:
        return None
    url = str(url).strip()
    
    # 1. Standard pattern: /restaurant/123456 or /place/123456
    match = re.search(r'/(?:place|restaurant|hospital|hairshop|nail|accommodation|stay|hotel|camping|resort|guestHouse|motel|pension|spa|studio|gym|academy|store)/(\d+)', url)
    if match:
        return match.group(1)
    
    # 2. General fallback for any alphanumeric path segment followed by digits (e.g. /barber/12345)
    match = re.search(r'/([a-zA-Z]+)/(\d+)', url)
    if match:
        return match.group(2)
        
    # 3. Simple fallback matching any sequence of digits in path/params
    match = re.search(r'/(\d+)', url)
    if match:
        return match.group(1)
        
    return None

def run_crawler(min_id=None, debug=False, sync=False):
    def dprint(*args, **kwargs):
        if debug:
            print(*args, **kwargs)
            
    last_id_file = os.path.join(script_dir, "last_id.txt")
    
    # 0. Load min_id from last_id.txt if not provided
    if min_id is None:
        if os.path.exists(last_id_file):
            try:
                with open(last_id_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        min_id = int(content)
                        dprint(f"   - 자동으로 이전 최종 ID({min_id})를 불러와 필터링을 적용합니다.")
            except ValueError:
                pass

    start_id = min_id if min_id is not None else 0
    session = requests.Session()
    
    # 1. Login to Rudolph-slot
    login_url = "http://rudolph-slot.club/login"
    login_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "content-type": "application/x-www-form-urlencoded",
        "Referer": login_url,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    login_payload = {
        "nickname": "rudolph",
        "password": "rltjrWkd"
    }
    
    dprint("1. 로그인을 시도합니다...")
    try:
        response = session.post(login_url, headers=login_headers, data=login_payload, allow_redirects=False, timeout=15)
        status_code = response.status_code
        location = response.headers.get("Location", "")
        
        if status_code == 302 and "/slot_list" in location:
            dprint("   - 로그인 성공 (302 /slot_list 리다이렉션 확인)")
        else:
            print("   - 로그인 실패 (오류: 리다이렉션 경로가 다릅니다.)")
            return
    except Exception as e:
        print(f"로그인 중 오류 발생: {e}")
        return

    # 2. Fetch slot lists
    data_url = "http://rudolph-slot.club/accounts/slots/all"
    data_headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/json",
        "x-requested-with": "XMLHttpRequest",
        "Referer": "http://rudolph-slot.club/slot_list",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Send full columns definition to enable returning 500 items per request
    data_payload = {
        "draw": 1,
        "columns": [
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
        ],
        "order": [{"column": 1, "dir": "desc", "name": "id"}],
        "start": 0,
        "length": -1,
        "search": {"value": "", "regex": False, "fixed": []},
        "slot_type": "6",
        "searched": "",
        "pageLength": -1,
        "_ts": int(time.time() * 1000),
        "sort_field": "id",
        "sort_dir": "desc"
    }

    all_data = []
    
    dprint("\n2. 슬롯 리스트 데이터 조회를 시작합니다 (전체 조회)...")
    try:
        data_response = session.post(data_url, headers=data_headers, json=data_payload, timeout=20)
        if not data_response.ok:
            print(f"     데이터 조회 실패: {data_response.reason}")
            return
            
        result = data_response.json()
        all_data = result.get("data", [])
        dprint(f"     전체 {len(all_data)}개 항목 로드 완료")
    except Exception as e:
        print(f"데이터 조회 중 오류 발생: {e}")
        return

    # 3. Filter items and find max ID
    max_id_val = None
    if all_data:
        try:
            max_id_val = max(int(item.get("id", 0)) for item in all_data if item.get("id") is not None)
        except ValueError:
            pass

    filtered_raw_data = []
    for item in all_data:
        if isinstance(item, dict):
            url = item.get("url")
            if not url or str(url).strip().lower() in ["none", "null", ""]:
                continue
                
            item_id = item.get("id")
            if min_id is not None:
                try:
                    if item_id is not None and int(item_id) <= min_id:
                        continue
                except ValueError:
                    pass
            filtered_raw_data.append(item)

    # 4. Group by start_date, end_date, and parsed place_id
    grouped = {}
    for item in filtered_raw_data:
        start_date = str(item.get("start_date", ""))
        end_date = str(item.get("end_date", ""))
        url = str(item.get("url", ""))
        place_id = extract_place_id(url)
        if not place_id:
            dprint(f"   [Warning] URL 파싱 실패: {url}")
            continue
            
        key = (start_date, end_date, place_id)
        
        try:
            curr_id = int(item.get("id", 0))
        except (ValueError, TypeError):
            curr_id = 0
            
        if key not in grouped:
            grouped[key] = {
                "max_id": curr_id,
                "start_date": start_date,
                "end_date": end_date,
                "place_id": place_id,
                "url": url,
                "slot_count": 1
            }
        else:
            grouped[key]["slot_count"] += 1
            grouped[key]["max_id"] = max(grouped[key]["max_id"], curr_id)

    sorted_groups = sorted(grouped.values(), key=lambda x: x["max_id"], reverse=True)

    # 5. Generate TSV including parsed place_id
    tsv_lines = ["start_date\tend_date\tplace_id\turl\tcount"]
    for g in sorted_groups:
        total_count = g["slot_count"] * 5
        tsv_lines.append(f"{g['start_date']}\t{g['end_date']}\t{g['place_id']}\t{g['url']}\t{total_count}")
    tsv_content = "\n".join(tsv_lines)
    
    # 6. Save log file
    log_dir = os.path.join(script_dir, "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    date_time_str = time.strftime("%m-%d_%H%M%S")
    end_id = max_id_val if max_id_val is not None else start_id
    output_file = os.path.join(log_dir, f"{date_time_str}_{start_id}-{end_id}.tsv")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(tsv_content)
        
    dprint(f"   - 최종 결과를 파일에 저장 완료: {output_file}\n")
    print(tsv_content)
    
    # 7. Update last_id.txt
    if max_id_val is not None:
        try:
            with open(last_id_file, "w") as f:
                f.write(str(max_id_val))
            dprint(f"   - 자동 기록: 최종 ID({max_id_val})를 {last_id_file}에 저장했습니다.")
        except Exception as e:
            dprint(f"   - 최종 ID 기록 실패: {e}")
            
        print(f"\n최종 ID: {max_id_val}")

    # 8. Sync directly to DB if requested and core is loaded
    if sync:
        if not HAS_CORE:
            print("오류: DB 동기화를 위한 core 모듈을 불러올 수 없습니다. 경로 설정을 확인하세요.")
            return
            
        print("\nDB 동기화를 시작합니다...")
        db_config = Config.get_db_config()
        import pymysql
        conn = pymysql.connect(**db_config, autocommit=False)
        try:
            kst_now = get_kst_now()
            # We want to sync for the target dates that Rudolph slots represent
            # Usually we sync for "today KST"
            target_date_str = get_kst_date().isoformat()
            
            # Filter slots active for today KST
            active_slots = []
            for item in all_data:
                url = str(item.get("url") or "").strip()
                p_id = extract_place_id(url)
                if not p_id:
                    continue
                start_date = item.get("start_date")
                end_date = item.get("end_date")
                if start_date and end_date and start_date <= target_date_str <= end_date:
                    active_slots.append(item)
            
            print(f"  [DB Sync] 오늘({target_date_str}) 활성인 슬롯 {len(active_slots)}개 확인.")
            
            with conn.cursor() as cursor:
                # Clear existing Rudolph records for today
                cursor.execute("""
                    DELETE FROM raw_slots_tmp 
                    WHERE site = 'RUDOLPH' AND work_date = %s
                """, (target_date_str,))
                dprint(f"  [DB Sync] 기존 {cursor.rowcount}개 데이터 삭제 완료.")
                
                # Insert individual slots (with their unique Rudolph slot id as sid)
                inserted_cnt = 0
                for item in active_slots:
                    sid = str(item.get("id"))
                    url = str(item.get("url"))
                    dest_id = extract_place_id(url)
                    # each slot represents 5 work count
                    work_count = 5
                    
                    cursor.execute("""
                        INSERT INTO raw_slots_tmp (site, sid, dest_id, work_count, work_date, created_at)
                        VALUES ('RUDOLPH', %s, %s, %s, %s, %s)
                    """, (sid, dest_id, work_count, target_date_str, kst_now))
                    inserted_cnt += 1
                
                conn.commit()
                print(f"  [DB Sync] 성공적으로 {inserted_cnt}개 슬롯을 raw_slots_tmp에 동기화 완료.")
        except Exception as e:
            conn.rollback()
            print(f"DB 동기화 중 오류 발생: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rudolph Slot Crawler")
    parser.add_argument("min_id", type=int, nargs="?", default=None, help="Filter results to show only items with ID greater than this value (overrides last_id.txt)")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logs")
    parser.add_argument("--sync", action="store_true", help="Sync fetched data directly to raw_slots_tmp database")
    args = parser.parse_args()
    
    run_crawler(min_id=args.min_id, debug=args.debug, sync=args.sync)
