import pymysql
import os
import psutil
import json
import sys
import threading
import random
from datetime import date, datetime, timedelta
from typing import Optional, Set, Any, Union
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import contextmanager

# Path adjustment to access core from admin folder
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Pooling support
from dbutils.pooled_db import PooledDB
from core.config import Config
from core.utils import get_kst_now, get_kst_date

# --- Global Connection Pool ---
db_pool = PooledDB(
    creator=pymysql,
    mincached=2,
    maxcached=10,
    maxconnections=20,
    blocking=True,
    **Config.get_db_config()
)

# Shared state (approximate)
active_devices: Set[str] = set()

# --- Database Helper ---
@contextmanager
def get_db_cursor():
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

app = FastAPI(title="Nmap Command Center PRO")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin API Summary with Anomaly Detection
@app.get("/api/v1/admin/summary")
async def get_admin_summary():
    kst_now, kst_date = get_kst_now(), get_kst_date()
    try:
        with get_db_cursor() as cursor:
            # 1. Task Summary Cards (Grouping by site_id to support FSD and test separately)
            cursor.execute("""
                SELECT 
                    rs.site_id,
                    SUM(rs.work_count) as target,
                    SUM(IFNULL(dp.success_cnt, 0)) as success,
                    SUM(IFNULL(dp.fail_cnt, 0)) as fail
                FROM raw_slots rs
                LEFT JOIN daily_progress dp ON rs.site_id = dp.site_id AND rs.dest_id = dp.dest_id AND dp.work_date = %s
                WHERE rs.status = 'on'
                  AND %s BETWEEN rs.start_date AND rs.end_date
                GROUP BY rs.site_id
            """, (kst_date, kst_date))
            rows = cursor.fetchall()
            
            stats_by_site = {row['site_id']: row for row in rows}
            fsd = stats_by_site.get('FSD', {'target': 0, 'success': 0, 'fail': 0})
            test = stats_by_site.get('test', {'target': 0, 'success': 0, 'fail': 0})
            
            fsd_target = fsd['target'] or 0
            fsd_success = fsd['success'] or 0
            fsd_fail = fsd['fail'] or 0
            
            test_target = test['target'] or 0
            test_success = test['success'] or 0
            test_fail = test['fail'] or 0
            
            summary_stats = {
                "fsd_target": fsd_target,
                "fsd_success": fsd_success,
                "fsd_fail": fsd_fail,
                "test_target": test_target,
                "test_success": test_success,
                "test_fail": test_fail,
                "total_target": fsd_target + test_target,
                "success": fsd_success + test_success,
                "fail": fsd_fail + test_fail,
                "remain": max(0, (fsd_target + test_target) - (fsd_success + test_success))
            }
            
            # 2. System Status
            disk = psutil.disk_usage('/')
            system_status = {
                "cpu": f"{psutil.cpu_percent()}%",
                "ram_mb": round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2),
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "kst_time": kst_now.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 3. Devices (Detailed)
            cursor.execute("""
                SELECT d.device_id, d.current_ip, d.memo, d.status, d.is_alert_muted,
                       tl.dest_name as current_dest,
                       tl.status as current_status,
                       tl.created_at as last_task_at,
                       IFNULL(ds.success_cnt, 0) as today_success, IFNULL(ds.fail_cnt, 0) as today_fail,
                       (SELECT MAX(end_time) FROM tasks_log WHERE device_id = d.device_id AND status='SUCCESS' AND work_date = %s) as last_success_at
                FROM devices d
                LEFT JOIN device_daily_stats ds ON d.device_id = ds.device_id AND ds.work_date = %s
                LEFT JOIN (
                    SELECT t1.device_id, t1.dest_name, t1.status, t1.created_at
                    FROM tasks_log t1
                    INNER JOIN (
                        SELECT device_id, MAX(id) as max_id 
                        FROM tasks_log 
                        GROUP BY device_id
                    ) t2 ON t1.id = t2.max_id
                ) tl ON d.device_id = tl.device_id
                ORDER BY d.memo ASC
            """, (kst_date, kst_date))
            devices_list = cursor.fetchall()

            # 4. Destinations (Detailed - all slots for today including status)
            cursor.execute("""
                SELECT p.dest_id, p.name, p.address, p.is_optimizer, p.check_status, p.dist_min_m, p.dist_max_m,
                       IFNULL(dp.success_cnt, 0) as success, IFNULL(dp.fail_cnt, 0) as fail,
                       rs_agg.target,
                       rs_agg.slot_status
                FROM (
                    SELECT dest_id, 
                           SUM(IF(status = 'on', work_count, 0)) as target,
                           MAX(status) as slot_status
                    FROM raw_slots
                    WHERE %s BETWEEN start_date AND end_date AND site_id <> 'test'
                    GROUP BY dest_id
                ) rs_agg
                JOIN places p ON rs_agg.dest_id = p.dest_id
                LEFT JOIN daily_progress dp ON p.dest_id = dp.dest_id AND dp.work_date = %s AND dp.site_id = 'FSD'
                ORDER BY slot_status DESC, success DESC
            """, (kst_date, kst_date))
            dest_list = cursor.fetchall()

            # 5. Live Alarms (Smart Anomaly Detection - Last 1 Hour)
            alarms = []
            one_hour_ago = kst_now - timedelta(hours=1)
            for d in devices_list:
                if d.get('is_alert_muted'):
                    continue
                if d['today_fail'] >= 5:
                    alarms.append({"type": "DEVICE", "level": "danger", "target": d['memo'] or d['device_id'], "msg": f"실패 급증 ({d['today_fail']}회)"})
                elif d['last_task_at'] and d['last_task_at'].replace(tzinfo=kst_now.tzinfo) > one_hour_ago:
                    if (kst_now - d['last_task_at'].replace(tzinfo=kst_now.tzinfo)).total_seconds() > 1200:
                        alarms.append({"type": "DEVICE", "level": "warning", "target": d['memo'] or d['device_id'], "msg": "20분 이상 무응답"})

            # 6. Recent Successes (Last 50 with Memo)
            cursor.execute("""
                SELECT l.dest_name, IFNULL(d.memo, l.device_id) as device_memo, l.start_time 
                FROM tasks_log l
                LEFT JOIN devices d ON l.device_id = d.device_id
                WHERE l.status='SUCCESS' 
                ORDER BY l.id DESC LIMIT 50
            """)
            recent_successes = cursor.fetchall()

            # 7. Recent Logs (For the log grid)
            cursor.execute("SELECT id, dest_name, device_id, status, ip, start_time, end_time FROM tasks_log ORDER BY id DESC LIMIT 100")
            recent_logs = cursor.fetchall()

            # 8. LTE Usage
            cursor.execute("SELECT modem_name, init_upload, init_download, now_upload, now_download, updated_at FROM lte_data_usage WHERE work_date = %s ORDER BY modem_name ASC", (kst_date,))
            lte_usage = cursor.fetchall()
            
        return {
            "summary": summary_stats,
            "system": system_status, "devices": devices_list, "destinations": dest_list, "logs": recent_logs, "lte": lte_usage, "alarms": alarms[:20],
            "success_feed": recent_successes
        }
    except Exception as e:
        print(f"Admin API Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/v1/admin/history/device/{device_id}")
async def get_device_history(device_id: str):
    kst_date = get_kst_date()
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT dest_name, status, DATE_FORMAT(start_time, '%%H:%%i') as time, 
                       TIMESTAMPDIFF(MINUTE, start_time, COALESCE(end_time, NOW())) as duration
                FROM tasks_log 
                WHERE device_id = %s AND work_date = %s 
                ORDER BY start_time DESC LIMIT 50
            """, (device_id, kst_date))
            return cursor.fetchall()
    except Exception as e: 
        print(f"Admin API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/dest/update")
async def update_destination(data: dict):
    dest_id, status, limit = data.get("dest_id"), data.get("status"), data.get("limit")
    try:
        with get_db_cursor() as cursor:
            if status: cursor.execute("UPDATE raw_slots SET status = %s WHERE dest_id = %s", (status, dest_id))
            if limit is not None: cursor.execute("UPDATE raw_slots SET work_count = %s WHERE dest_id = %s AND status='on'", (limit, dest_id))
        return {"status": "ok"}
    except Exception as e: 
        print(f"Admin API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/device/toggle_mute")
async def toggle_device_mute(data: dict):
    device_id = data.get("device_id")
    is_muted = data.get("is_muted")
    if not device_id or is_muted is None:
        raise HTTPException(status_code=400, detail="Missing device_id or is_muted")
    try:
        with get_db_cursor() as cursor:
            cursor.execute("UPDATE devices SET is_alert_muted = %s WHERE device_id = %s", (1 if is_muted else 0, device_id))
        return {"status": "ok", "device_id": device_id, "is_alert_muted": is_muted}
    except Exception as e:
        print(f"Admin API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

ADMIN_DIR = os.path.dirname(os.path.abspath(__file__))

# Page Endpoints for HTML5 History Routing
@app.get("/summary", response_class=HTMLResponse)
@app.get("/devices", response_class=HTMLResponse)
@app.get("/destinations", response_class=HTMLResponse)
@app.get("/logs", response_class=HTMLResponse)
@app.get("/lte", response_class=HTMLResponse)
async def serve_admin_pages(request: Request):
    index_path = os.path.join(ADMIN_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# Static Files
app.mount("/", StaticFiles(directory=ADMIN_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
