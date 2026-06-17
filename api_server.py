import pymysql
import random
import os
import secrets
import uuid
import hashlib
import json
import re
import asyncio
import psutil
import time
import threading
from datetime import date, datetime, timedelta
from typing import Optional, Set, Any, Union
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import contextmanager

# Pooling support
from dbutils.pooled_db import PooledDB

# Import refactored core logic
from core.config import Config
from core.utils import generate_spoofed_identity, calculate_gps_and_speed, get_kst_now, get_kst_date
from core.scraper import NaverPlaceScraper
from core.admin_api import register_admin_endpoints

# --- Configuration & Safety Rules ---
IP_EXCLUSIVITY_DAYS = 0
WORKING_LOCK_SEC = 300 # 5 Minute to wait for client progress report

# --- Global Allocation Lock ---
allocation_lock = threading.Lock()

# --- Global Connection Pool ---
db_pool = PooledDB(
    creator=pymysql,
    mincached=5,
    maxcached=20,
    maxconnections=50,
    blocking=True,
    **Config.get_db_config()
)

scraper_instance = NaverPlaceScraper()

# --- Monitoring State ---
request_counter = 0
active_devices: Set[str] = set()
last_net_io = psutil.net_io_counters()

def sync_device_ip_to_legacy(device_id: str, ip: str):
    if not ip or ip == "Unknown" or ip == "0.0.0.0": return
    try:
        conf = Config.get_source_fsd_config()
        if not conf.get('host'): return
        conn = pymysql.connect(**conf, autocommit=True)
        with conn.cursor() as cursor:
            cursor.execute("UPDATE devices SET current_ip=%s, ip_updated_at=NOW() WHERE device_id=%s", (ip, device_id))
        conn.close()
    except: pass

def sync_legacy_task_start(device_id: str, dest_id: str, dest_name: str, ip: str, start_time, distance_m: int, msg: str):
    try:
        conf = Config.get_source_fsd_config()
        if not conf.get('host'): return
        conn = pymysql.connect(**conf, autocommit=True)
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO task_log (device_id, dest_id, dest_name, ip, status, start_time, distance_m) VALUES (%s, %s, %s, %s, 'ALLOCATED', %s, %s)", 
                           (device_id, dest_id, dest_name, ip, start_time, distance_m))
        conn.close()
    except Exception as e: print(f"[Sync-Legacy] Start Error: {e}")

def sync_legacy_task_status_update(device_id: str, status: str, end_time, ip: str = None, client_dist: int = 0, client_time: int = 0):
    try:
        conf = Config.get_source_fsd_config()
        if not conf.get('host'): return
        conn = pymysql.connect(**conf, autocommit=True)
        with conn.cursor() as cursor:
            update_parts = ["status=%s", "end_time=%s", "distance_m=%s", "duration_sec=%s"]
            params = [status, end_time, client_dist, client_time]
            if ip and ip != "Unknown":
                update_parts.append("ip=%s")
                params.append(ip)
            params.append(device_id)
            cursor.execute(f"UPDATE task_log SET {', '.join(update_parts)} WHERE device_id=%s AND status NOT LIKE '%%SUCCESS%%' AND status NOT LIKE '%%FAIL%%' ORDER BY id DESC LIMIT 1", params)
        conn.close()
    except Exception as e: print(f"[Sync-Legacy] Update Error: {e}")

def sync_legacy_task_end(site_id: str, device_id: str, dest_id: str, status: str, end_time, client_dist: int, client_time: int, msg: str):
    if site_id == 'test': return
    try:
        sync_legacy_task_status_update(device_id, status, end_time, client_dist=client_dist, client_time=client_time)
        conf = Config.get_source_fsd_config()
        if not conf.get('host'): return
        conn = pymysql.connect(**conf, autocommit=True)
        with conn.cursor() as cursor:
            if status == 'SUCCESS':
                cursor.execute("UPDATE daily_tasks SET success_count = success_count + 1, last_success_at = %s WHERE dest_id = %s AND work_date = CURDATE()", (end_time, dest_id))
        conn.close()
    except Exception as e: print(f"[Sync-Legacy] End Error: {e}")

def format_address(addr: Optional[str]) -> Optional[str]:
    """
    주소 가공: 첫 번째 단어(시/도)만 제거하여 매칭률 향상.
    예: '서울특별시 동작구 상도로' -> '동작구 상도로'
    """
    if not addr: return addr
    parts = addr.strip().split(' ')
    if len(parts) > 1:
        return ' '.join(parts[1:]).strip()
    return addr.strip()

app = FastAPI(title="Nmap Production API v1")

import sys
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    try:
        body = await request.body()
        err_msg = f"[Validation Error] Path: {request.url.path} | Detail: {exc.errors()} | Body: {body.decode('utf-8', errors='ignore')}\n"
        sys.stderr.write(err_msg)
        sys.stderr.flush()
    except Exception as e:
        sys.stderr.write(f"[Validation Error Handler Error]: {e}\n")
        sys.stderr.flush()
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# Mount Admin Dashboard
app.mount("/admin", StaticFiles(directory="admin", html=True), name="admin")
register_admin_endpoints(app, get_db_cursor=lambda: db_pool.connection().cursor(pymysql.cursors.DictCursor), active_devices=active_devices)

# Models
class TaskRequest(BaseModel):
    device_id: str
    ip: Optional[str] = "0.0.0.0"
    site_id: Optional[str] = None
    arrival_time: Optional[Union[int, str]] = None

class StatusUpdate(BaseModel):
    task_id: Optional[Union[int, str]] = None
    log_id: Optional[Union[int, str]] = None
    device_id: Optional[str] = None
    status: str
    drive_dist: Optional[Any] = None
    drive_time: Optional[Any] = None
    calc_speed: Optional[Any] = None
    real_ip: Optional[str] = None
    actual_address: Optional[str] = None
    requested_address: Optional[str] = None
    error_msg: Optional[str] = None
    log_path: Optional[str] = None

class ResultReport(BaseModel):
    task_id: Optional[Union[int, str]] = None
    log_id: Optional[Union[int, str]] = None
    device_id: str
    status: str
    message: Optional[str] = None
    requested_address: Optional[str] = None
    actual_address: Optional[str] = None
    log_path: Optional[str] = None
    drive_dist: Optional[Any] = None
    drive_time: Optional[Any] = None
    calc_speed: Optional[Any] = None

class LteUsageReport(BaseModel):
    name: str
    upload: int
    download: int

@contextmanager
def get_db_cursor():
    """Fetches a connection from the global pool and provides a cursor."""
    conn = db_pool.connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# --- Device Metrics Helper ---
def update_device_stats(cursor, device_id, success=0, fail=0, alloc_fail=0, duration=0):
    kst_now, kst_date = get_kst_now(), get_kst_date()
    sql = """
        INSERT INTO device_daily_stats (device_id, work_date, success_cnt, fail_cnt, alloc_fail_cnt, total_duration_sec, last_active_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            success_cnt = success_cnt + VALUES(success_cnt),
            fail_cnt = fail_cnt + VALUES(fail_cnt),
            alloc_fail_cnt = alloc_fail_cnt + VALUES(alloc_fail_cnt),
            total_duration_sec = total_duration_sec + VALUES(total_duration_sec),
            last_active_at = VALUES(last_active_at)
    """
    cursor.execute(sql, (device_id, kst_date, success, fail, alloc_fail, duration, kst_now))

def log_allocation_failure(cursor, device_id, error_msg, ip, payload=None):
    """Logs detailed allocation failure reasons for debugging/monitoring."""
    kst_now = get_kst_now()
    cursor.execute("INSERT INTO allocation_failures (device_id, error_msg, kst_time, ip, payload) VALUES (%s, %s, %s, %s, %s)", 
                   (device_id, error_msg, kst_now, ip, json.dumps(payload) if payload else None))

# --- Background Monitoring Task ---
async def log_system_metrics():
    global request_counter, active_devices, last_net_io
    while True:
        try:
            cpu, ram_mb = psutil.cpu_percent(interval=1), psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            disk = psutil.disk_usage('/')
            disk_free_gb, disk_total_gb = round(disk.free / (1024**3), 2), round(disk.total / (1024**3), 2)
            curr_net_io = psutil.net_io_counters()
            net_sent_mb, net_recv_mb = round((curr_net_io.bytes_sent - last_net_io.bytes_sent) / (1024 * 1024), 2), round((curr_net_io.bytes_recv - last_net_io.bytes_recv) / (1024 * 1024), 2)
            last_net_io, devices_cnt, req_cnt = curr_net_io, len(active_devices), request_counter
            request_counter, active_devices.clear()
            kst_now = get_kst_now()
            with get_db_cursor() as cursor:
                pool_used = db_pool._conns[0].size if hasattr(db_pool, '_conns') else 0
                cursor.execute("""
                    INSERT INTO system_metrics (heartbeat_at, cpu_usage, ram_usage_mb, disk_free_gb, disk_total_gb, active_devices, total_req, net_sent_mb, net_recv_mb, db_pool_used)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (kst_now, cpu, ram_mb, disk_free_gb, disk_total_gb, devices_cnt, req_cnt, net_sent_mb, net_recv_mb, pool_used))
                
                # Cleanup: Keep only last 7 days of optimizer success logs and IP allocation history
                cursor.execute("DELETE FROM optimizer_success_logs WHERE created_at < NOW() - INTERVAL 7 DAY")
                cursor.execute("DELETE FROM ip_allocation_history WHERE allocated_at < NOW() - INTERVAL 7 DAY")
        except Exception as e: print(f"Monitoring Error: {e}")
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event(): asyncio.create_task(log_system_metrics())

# --- Health & Dashboard ---
@app.get("/api/v1/health")
async def health_check():
    try:
        with get_db_cursor() as cursor: cursor.execute("SELECT 1")
        disk, net, kst_now = psutil.disk_usage('/'), psutil.net_io_counters(), get_kst_now()
        return {"status": "healthy", "kst_time": kst_now.strftime('%Y-%m-%d %H:%M:%S'), "uptime": str(kst_now - datetime.fromtimestamp(psutil.Process(os.getpid()).create_time(), kst_now.tzinfo)).split('.')[0], "cpu": f"{psutil.cpu_percent()}%", "ram_mb": round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2), "disk": {"free_gb": round(disk.free / (1024**3), 2), "total_gb": round(disk.total / (1024**3), 2), "percent": f"{disk.percent}%"}, "network_cumulative_mb": {"sent": round(net.bytes_sent / (1024 * 1024), 2), "recv": round(net.bytes_recv / (1024 * 1024), 2)}, "active_devices_now": len(active_devices), "db": "connected"}
    except Exception as e: return {"status": "unhealthy", "error": str(e)}

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    kst_now = get_kst_now()
    return f"<h1>Nmap Production API v1 Active</h1><p>KST: {kst_now.strftime('%Y-%m-%d %H:%M:%S')}</p><p><a href='/admin/'>Go to Admin Dashboard</a></p><p><a href='/api/v1/health'>Check Health Metrics</a></p>"

# --- Device Task API ---

@app.post("/api/v1/request_task")
async def request_task(req: TaskRequest):
    global request_counter, active_devices
    request_counter += 1
    active_devices.add(req.device_id)
    kst_now, kst_date = get_kst_now(), get_kst_date()
    client_ip = req.ip if req.ip and req.ip != "0.0.0.0" and req.ip != "unknown" else None
    
    try:
        with allocation_lock:
            with get_db_cursor() as cursor:
                update_device_stats(cursor, req.device_id)
                
                # 1. Device Verification
                cursor.execute("SELECT seq, device_id, status, orig_ssaid, orig_adid, orig_idfv, orig_ni, orig_token FROM devices WHERE device_id = %s AND status = 'on'", (req.device_id,))
                device_row = cursor.fetchone()
                if not device_row: 
                    log_allocation_failure(cursor, req.device_id, "UNAUTHORIZED_DEVICE", client_ip or "unknown", req.dict())
                    return {"status": "error", "msg": "UNAUTHORIZED_DEVICE"}

                # 2. Safety Exclusions (Strict 5-Minute Lock)
                # Check for any task created within the lock period that hasn't been completed yet (end_time IS NULL)
                cursor.execute("SELECT dest_id FROM tasks_log WHERE end_time IS NULL AND created_at > %s - INTERVAL %s SECOND", (kst_now, WORKING_LOCK_SEC))
                locked_dest_ids = {str(row['dest_id']) for row in cursor.fetchall()}

                # IP Exclusivity: Same IP cannot take same dest_id on the same KST day
                if client_ip:
                    cursor.execute("SELECT dest_id FROM ip_allocation_history WHERE ip = %s AND allocated_at >= %s", (client_ip, kst_date))
                    ip_allocated_ids = {str(row['dest_id']) for row in cursor.fetchall()}
                else:
                    ip_allocated_ids = set()

                # 3. Candidate Selection
                base_query = """
                    SELECT 
                        s.site_id, min(s.sid) as sid, s.dest_id, p.name, p.address, p.lat, p.lng, 
                        p.arr_min_s, p.arr_max_s, p.dist_min_m, p.dist_max_m, p.check_status, p.is_optimizer,
                        SUM(s.work_count) as total_target, IFNULL(dp.success_cnt, 0) as total_success,
                        SUM(s.work_count) - IFNULL(dp.success_cnt, 0) as remain_count,
                        IFNULL(dp.fail_cnt, 0) as fail_cnt, IFNULL(dp.alloc_fail_cnt, 0) as alloc_fail_cnt,
                        IFNULL(dp.last_dist_m, 800) as last_dist_m
                    FROM raw_slots s
                    LEFT JOIN places p ON s.dest_id = p.dest_id
                    LEFT JOIN daily_progress dp ON s.site_id = dp.site_id AND s.dest_id = dp.dest_id AND dp.work_date = %s
                    WHERE s.status = 'on' AND %s BETWEEN s.start_date AND s.end_date
                      AND (p.check_status IS NULL OR p.check_status <> 'FAIL')
                """
                params = [kst_date, kst_date]
                if req.site_id: base_query += " AND s.site_id = %s"; params.append(req.site_id)
                else: base_query += " AND s.site_id <> 'test'"
                
                base_query += """
                    GROUP BY s.site_id, s.dest_id
                    HAVING remain_count > 0 AND fail_cnt < 10
                """
                cursor.execute(base_query, tuple(params))
                all_raw_candidates = cursor.fetchall()
                
                # 우선순위 그룹핑
                group_zero = [] # 1순위: 성공 0회 (최초 시도)
                group_fail = [] # 2순위: 실패가 있는 것 (검증 필요)
                group_rest = [] # 3순위: 일반 (성공 이력 있음)
                
                for cand in all_raw_candidates:
                    dest_id = str(cand['dest_id'])
                    if dest_id in locked_dest_ids or dest_id in ip_allocated_ids: continue
                    
                    if cand['total_success'] == 0:
                        group_zero.append(cand)
                    elif cand['fail_cnt'] > 0:
                        group_fail.append(cand)
                    else:
                        group_rest.append(cand)

                # 할당 결정
                if group_zero: 
                    task = random.choice(group_zero)
                elif group_fail:
                    # 실패가 높은 순으로 정렬 후 상위권에서 랜덤 선택
                    group_fail.sort(key=lambda x: x['fail_cnt'], reverse=True)
                    task = random.choice(group_fail[:max(1, len(group_fail)//2 + 1)])
                elif group_rest:
                    # 성공 횟수가 적은 순으로 정렬 후 상위권에서 랜덤 선택
                    group_rest.sort(key=lambda x: x['total_success'])
                    task = random.choice(group_rest[:max(1, len(group_rest)//2 + 1)])
                else: 
                    log_allocation_failure(cursor, req.device_id, "NO_TASK_AVAILABLE", client_ip or "unknown", req.dict())
                    return {"status": "error", "msg": "NO_TASK_AVAILABLE"}

                # Record IP allocation for exclusivity check
                if client_ip:
                    cursor.execute("INSERT INTO ip_allocation_history (ip, dest_id, allocated_at) VALUES (%s, %s, %s)", (client_ip, task['dest_id'], kst_now))

                cursor.execute("SELECT keyword FROM place_keywords WHERE dest_id = %s AND status = 'on'", (task['dest_id'],))
                keywords = [row['keyword'] for row in cursor.fetchall()]
                if not keywords: keywords = [task['name']]
                random.shuffle(keywords)
                
                final_arrival_s = req.arrival_time if req.arrival_time and int(req.arrival_time) > 0 else random.randint(int(task['arr_min_s']), int(task['arr_max_s']))
                if final_arrival_s < 300: final_arrival_s = 300

                is_optimizer_target = bool(task['is_optimizer'])
                final_lat, final_lng, final_dist, final_speed, found_visible, search_keyword = 0.0, 0.0, 0.0, 0.0, False, keywords[0]
                d_min_m, d_max_m, last_successful_dist = int(task['dist_min_m']), min(int(task['dist_max_m']), 10000), int(task.get('last_dist_m', 800))

                if is_optimizer_target:
                    print(f"[*] Gradual Inspection: {task['name']} (Baseline: {last_successful_dist}m)")
                    
                    found_any_keyword = False
                    dist = 0.0
                    for kw in keywords:
                        if found_any_keyword: break
                        search_keyword = kw
                        
                        # 3-Stage Hybrid Search Logic
                        distances_to_test = [d_max_m] # 1. Max Probe
                        
                        exp_dist = last_successful_dist + 2000 # 2. Expansion Probe
                        if d_min_m < exp_dist < d_max_m:
                            distances_to_test.append(exp_dist)
                            
                        # 3. Local Step-down
                        start_step = min(last_successful_dist + 500, d_max_m)
                        if start_step < d_min_m: start_step = d_min_m
                        
                        curr_dist = start_step
                        while curr_dist >= d_min_m:
                            if curr_dist not in distances_to_test:
                                distances_to_test.append(curr_dist)
                            curr_dist -= 200
                            
                        if d_min_m not in distances_to_test:
                            distances_to_test.append(d_min_m)

                        for target_dist in distances_to_test:
                            if found_any_keyword: break
                            t_max = target_dist
                            t_min = max(d_min_m, t_max - 200)
                            if t_min >= t_max: t_min = max(0, t_max - 50)
                            
                            # Try a few different random coordinates (angles) at this distance range
                            for _ in range(2):
                                s_lat, s_lng, dist, _ = calculate_gps_and_speed(float(task['lat']), float(task['lng']), t_min, t_max, 0, 0, fixed_arrival_s=final_arrival_s)
                                try:
                                    res = scraper_instance._mobile_search(search_keyword, lat=str(s_lat), lng=str(s_lng), timeout=3)
                                    pl = res.get("place", [])
                                    idx = next((i for i, p in enumerate(pl) if str(p.get('id')) == str(task['dest_id'])), -1)
                                    rank = len(res.get("ac", [])) + idx + 1 if idx != -1 else 99
                                    if rank == 99:
                                        for i, a in enumerate(res.get("ac", [])):
                                            if isinstance(a, dict) and str(a.get('id')) == str(task['dest_id']): rank = i + 1; break
                                    if rank <= 8:
                                        final_lat, final_lng, final_dist, found_visible, found_any_keyword = s_lat, s_lng, dist, True, True
                                        # Log success for future emergency reuse (7 days retention)
                                        cursor.execute("INSERT INTO optimizer_success_logs (dest_id, site_id, keyword, lat, lng, distance_m) VALUES (%s, %s, %s, %s, %s, %s)", 
                                                       (task['dest_id'], task['site_id'], search_keyword, s_lat, s_lng, int(dist)))
                                        break
                                except: pass

                        if not found_visible:
                             cursor.execute("UPDATE daily_progress SET alloc_fail_cnt = alloc_fail_cnt + 1 WHERE work_date=%s AND site_id=%s AND dest_id=%s", (kst_date, task['site_id'], task['dest_id']))
                    
                    if found_visible:
                        final_speed = round((final_dist / 1000.0) / (final_arrival_s / 3600.0), 2)
                        if final_speed < 10.0:
                            final_arrival_s = max(60, int((final_dist / 1000.0) / 10.0 * 3600))
                            final_speed = 10.0
                    else:
                        update_device_stats(cursor, req.device_id, alloc_fail=1)
                        cursor.execute("INSERT INTO keyword_allocation_failures (work_date, site_id, dest_id, dest_name, search_keyword, device_id, last_dist_m, last_rank) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (kst_date, task['site_id'], task['dest_id'], task['name'], search_keyword, req.device_id, int(dist), 99))
                        log_allocation_failure(cursor, req.device_id, f"VISIBILITY_NOT_GUARANTEED: {task['name']}", client_ip, req.dict())
                        return {"status": "error", "msg": "VISIBILITY_NOT_GUARANTEED"}
                else:
                    final_lat, final_lng, final_dist, _ = calculate_gps_and_speed(float(task['lat']), float(task['lng']), d_min_m, d_max_m, 0, 0, fixed_arrival_s=final_arrival_s)
                    final_speed = round((final_dist / 1000.0) / (final_arrival_s / 3600.0), 2)
                    if final_speed < 10.0:
                        final_arrival_s = max(60, int((final_dist / 1000.0) / 10.0 * 3600))
                        final_speed = 10.0

                # 5. Identity Spoofing
                spoofed_id = generate_spoofed_identity()
                original_id = {"ssaid": device_row["orig_ssaid"], "adid": device_row["orig_adid"], "idfv": device_row["orig_idfv"], "ni": device_row["orig_ni"], "token": device_row["orig_token"]}

                # 6. Final Insertion & Response
                msg_str = f"Start: {final_lat},{final_lng} | GoalTime: {final_arrival_s}s | Speed: {final_speed}km/h | Keyword: {search_keyword}"
                cursor.execute("""
                    INSERT INTO tasks_log (work_date, site_id, sid, dest_id, dest_name, device_id, ip, spoofed_identity, status, result_msg, start_time, distance_m, speed_kmh, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'WORKING', %s, %s, %s, %s, %s)
                """, (kst_date, task['site_id'], task['sid'], task['dest_id'], task['name'], req.device_id, client_ip, json.dumps(spoofed_id), msg_str, kst_now, int(final_dist), final_speed, kst_now))
                
                # Legacy Dashboard Real-time Sync
                if client_ip: sync_device_ip_to_legacy(req.device_id, client_ip)
                sync_legacy_task_start(req.device_id, task['dest_id'], task['name'], client_ip, kst_now, int(final_dist), msg_str)
                
                return {"status": "ok", "task_id": cursor.connection.insert_id(), "device_seq": device_row['seq'], "destination": {"id": task['dest_id'], "target_name": task['name'], "search_keyword": search_keyword, "address": format_address(task['address']), "lat": float(task['lat']), "lng": float(task['lng'])}, "start_pos": {"lat": final_lat, "lng": final_lng, "speed_kmh": final_speed, "dist_m": final_dist}, "arrival_time": final_arrival_s, "identity": {"original": original_id, "spoofed": spoofed_id}}
    except Exception as e: print(f"CRITICAL ERROR: {req.device_id}: {e}"); raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/api/v1/report_result")
async def report_result(report: ResultReport):
    global request_counter
    request_counter += 1
    actual_task_id = report.task_id or report.log_id
    if not actual_task_id:
        return {"status": "REPORTED"}
    kst_now, kst_date = get_kst_now(), get_kst_date()
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT status, site_id, dest_id, distance_m, ip FROM tasks_log WHERE id = %s", (actual_task_id,))
            task_row = cursor.fetchone()
            if not task_row or task_row['status'] not in ['WORKING', 'RUNNING']: return {"status": "REPORTED"}
            
            client_dist = int(report.drive_dist) if report.drive_dist and str(report.drive_dist).isdigit() else 0
            client_time = int(report.drive_time) if report.drive_time and str(report.drive_time).isdigit() else 0
            client_speed = float(report.calc_speed) if report.calc_speed else 0.0

            cursor.execute("UPDATE tasks_log SET status = %s, result_msg = %s, end_time = %s, client_dist_m = %s, client_time_s = %s, client_speed_kmh = %s WHERE id = %s", (report.status, report.message, kst_now, client_dist, client_time, client_speed, actual_task_id))
            
            if report.status == 'SUCCESS':
                update_device_stats(cursor, report.device_id, success=1)
                cursor.execute("INSERT INTO ip_success_history (ip, dest_id, last_success_at) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE last_success_at = VALUES(last_success_at)", (task_row['ip'], task_row['dest_id'], kst_now))
                cursor.execute("INSERT INTO daily_progress (work_date, site_id, dest_id, success_cnt, fail_cnt, alloc_fail_cnt, last_dist_m, last_success_at) VALUES (%s, %s, %s, 1, 0, 0, %s, %s) ON DUPLICATE KEY UPDATE success_cnt=success_cnt+1, last_success_at=VALUES(last_success_at), fail_cnt=0, alloc_fail_cnt=0, last_dist_m=VALUES(last_dist_m)", (kst_date, task_row['site_id'], task_row['dest_id'], task_row['distance_m'], kst_now))
                
                # Sync back to Legacy Server
                sync_legacy_task_end(task_row['site_id'], report.device_id, task_row['dest_id'], 'SUCCESS', kst_now, client_dist, client_time, report.message)
            else:
                update_device_stats(cursor, report.device_id, fail=1)
                cursor.execute("INSERT INTO daily_progress (work_date, site_id, dest_id, success_cnt, fail_cnt, alloc_fail_cnt, last_dist_m, last_fail_at) VALUES (%s, %s, %s, 0, 1, 0, %s, %s) ON DUPLICATE KEY UPDATE fail_cnt=fail_cnt+1, last_fail_at=VALUES(last_fail_at)", (kst_date, task_row['site_id'], task_row['dest_id'], task_row['distance_m'], kst_now))
                
                # Sync back to Legacy Server
                sync_legacy_task_end(task_row['site_id'], report.device_id, task_row['dest_id'], report.status, kst_now, client_dist, client_time, report.message)
            return {"status": "REPORTED"}
    except Exception as e: print(f"ERROR: {e}"); raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/api/v1/update_status")
async def update_status(data: StatusUpdate):
    global request_counter
    request_counter += 1
    actual_task_id = data.task_id or data.log_id
    if not actual_task_id:
        return {"status": "UPDATED"}
    kst_now, kst_date = get_kst_now(), get_kst_date()
    
    def safe_int(val):
        if not val: return None
        try: return int(float(val))
        except: return None
        
    try:
        with get_db_cursor() as cursor:
            d_time = safe_int(data.drive_time)
            d_dist = safe_int(data.drive_dist)
            if data.device_id:
                update_device_stats(cursor, data.device_id, duration=d_time if d_time else 0)
                if data.real_ip and data.real_ip != "Unknown": 
                    cursor.execute("UPDATE devices SET current_ip=%s, ip_updated_at=%s WHERE device_id=%s", (data.real_ip, kst_now, data.device_id))
                    sync_device_ip_to_legacy(data.device_id, data.real_ip)
                
            update_parts, params = ["status = %s"], [data.status]
            if data.status in ['SUCCESS', 'FAIL'] or data.status.startswith('FAIL'): update_parts.append("end_time = %s"); params.append(kst_now)
            if data.real_ip and data.real_ip != "Unknown": update_parts.append("ip = %s"); params.append(data.real_ip)
            if d_dist is not None: update_parts.append("distance_m = %s"); params.append(d_dist)
            if d_time is not None: update_parts.append("duration_sec = %s"); params.append(d_time)
            status_str = data.status
            if data.actual_address or data.error_msg:
                status_str = f"{data.status} | Req:{data.requested_address} | Act:{data.actual_address} | Msg:{data.error_msg}"
                if data.status in ['SUCCESS', 'FAIL'] or data.status.startswith('FAIL'): update_parts.append("result_msg = %s"); params.append(status_str)
            cursor.execute(f"UPDATE tasks_log SET {', '.join(update_parts)} WHERE id = %s", (*params, actual_task_id))
            
            # Sync ALL status updates to legacy (IP_CHANGED, DRIVING, etc)
            if data.device_id and data.status not in ['SUCCESS', 'FAIL'] and not data.status.startswith('FAIL'):
                sync_legacy_task_status_update(data.device_id, data.status, kst_now, ip=data.real_ip, client_dist=d_dist or 0, client_time=d_time or 0)
                
            if data.status in ['SUCCESS', 'FAIL'] or data.status.startswith('FAIL'):
                cursor.execute("SELECT site_id, dest_id, distance_m, ip FROM tasks_log WHERE id = %s", (actual_task_id,))
                row = cursor.fetchone()
                if row:
                    msg_for_legacy = data.error_msg if data.error_msg else data.status
                    if data.status == 'SUCCESS': 
                        if data.device_id:
                            update_device_stats(cursor, data.device_id, success=1)
                        cursor.execute("INSERT INTO ip_success_history (ip, dest_id, last_success_at) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE last_success_at = VALUES(last_success_at)", (row['ip'], row['dest_id'], kst_now))
                        cursor.execute("INSERT INTO daily_progress (work_date, site_id, dest_id, success_cnt, fail_cnt, alloc_fail_cnt, last_dist_m, last_success_at) VALUES (%s, %s, %s, 1, 0, 0, %s, %s) ON DUPLICATE KEY UPDATE success_cnt=success_cnt+1, last_success_at=VALUES(last_success_at), fail_cnt=0, alloc_fail_cnt=0, last_dist_m=VALUES(last_dist_m)", (kst_date, row['site_id'], row['dest_id'], row['distance_m'], kst_now))
                        
                        # Sync back to Legacy Server
                        if data.device_id:
                            sync_legacy_task_end(row['site_id'], data.device_id, row['dest_id'], 'SUCCESS', kst_now, d_dist or 0, d_time or 0, msg_for_legacy)
                    else: 
                        if data.device_id:
                            update_device_stats(cursor, data.device_id, fail=1)
                        cursor.execute("INSERT INTO daily_progress (work_date, site_id, dest_id, success_cnt, fail_cnt, alloc_fail_cnt, last_dist_m, last_fail_at) VALUES (%s, %s, %s, 0, 1, 0, %s, %s) ON DUPLICATE KEY UPDATE fail_cnt=fail_cnt+1, last_fail_at=VALUES(last_fail_at)", (kst_date, row['site_id'], row['dest_id'], row['distance_m'], kst_now))
                        
                        # Sync back to Legacy Server
                        if data.device_id:
                            sync_legacy_task_end(row['site_id'], data.device_id, row['dest_id'], data.status, kst_now, d_dist or 0, d_time or 0, msg_for_legacy)
        return {"status": "UPDATED"}
    except Exception as e: print(f"Error: {e}"); raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/api/v1/lte_usage")
async def report_lte_usage(report: LteUsageReport):
    kst_date = get_kst_date()
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT id FROM lte_data_usage WHERE modem_name = %s AND work_date = %s", (report.name, kst_date))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE lte_data_usage 
                    SET now_upload = %s, now_download = %s 
                    WHERE id = %s
                """, (report.upload, report.download, row['id']))
            else:
                cursor.execute("""
                    INSERT INTO lte_data_usage (modem_name, work_date, init_upload, init_download, now_upload, now_download) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (report.name, kst_date, report.upload, report.download, report.upload, report.download))
        return {"status": "ok"}
    except Exception as e: 
        print(f"LTE Usage Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

if __name__ == "__main__":
    import uvicorn; uvicorn.run(app, host="0.0.0.0", port=Config.get_api_port())
