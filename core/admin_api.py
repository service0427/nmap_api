import os
import psutil
import pymysql
import json
from datetime import datetime
from fastapi import HTTPException
from fastapi.responses import JSONResponse

def get_kst_now():
    from datetime import timedelta, timezone
    return datetime.now(timezone(timedelta(hours=9)))

def get_kst_date():
    return get_kst_now().date()

def register_admin_endpoints(app, get_db_cursor, active_devices):
    @app.get("/api/v1/admin/summary")
    async def get_admin_summary():
        kst_now, kst_date = get_kst_now(), get_kst_date()
        try:
            with get_db_cursor() as cursor:
                # 1. Summary Cards
                cursor.execute("SELECT SUM(work_count) as total FROM raw_slots WHERE status='on' AND %s BETWEEN start_date AND end_date", (kst_date,))
                total_target = cursor.fetchone()['total'] or 0
                cursor.execute("SELECT SUM(success_cnt) as s, SUM(fail_cnt) as f FROM daily_progress WHERE work_date = %s", (kst_date,))
                prog = cursor.fetchone()
                success_cnt, fail_cnt = prog['s'] or 0, prog['f'] or 0
                
                # 2. System Status
                disk = psutil.disk_usage('/')
                system_status = {
                    "cpu": f"{psutil.cpu_percent()}%", 
                    "ram_mb": round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2),
                    "disk_free_gb": round(disk.free / (1024**3), 2), 
                    "active_devices": len(active_devices), 
                    "kst_time": kst_now.strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # 3. Devices
                cursor.execute("""
                    SELECT d.device_id, d.current_ip, d.memo, d.status,
                           (SELECT dest_name FROM tasks_log WHERE device_id = d.device_id ORDER BY id DESC LIMIT 1) as current_dest,
                           (SELECT status FROM tasks_log WHERE device_id = d.device_id ORDER BY id DESC LIMIT 1) as current_status,
                           IFNULL(ds.success_cnt, 0) as today_success, IFNULL(ds.fail_cnt, 0) as today_fail
                    FROM devices d
                    LEFT JOIN device_daily_stats ds ON d.device_id = ds.device_id AND ds.work_date = %s
                    ORDER BY d.memo ASC
                """, (kst_date,))
                devices_list = cursor.fetchall()

                # 4. Destinations
                cursor.execute("""
                    SELECT p.dest_id, p.name, p.address, p.is_optimizer, p.dist_min_m, p.dist_max_m,
                           IFNULL(dp.success_cnt, 0) as success, IFNULL(dp.fail_cnt, 0) as fail,
                           (SELECT SUM(work_count) FROM raw_slots WHERE dest_id = p.dest_id AND status='on' AND %s BETWEEN start_date AND end_date) as target
                    FROM places p
                    LEFT JOIN daily_progress dp ON p.dest_id = dp.dest_id AND dp.work_date = %s
                    WHERE p.id IN (SELECT DISTINCT id FROM (SELECT p2.id FROM places p2 JOIN raw_slots rs ON p2.dest_id = rs.dest_id WHERE rs.status='on') t)
                    ORDER BY success DESC
                """, (kst_date, kst_date))
                dest_list = cursor.fetchall()

                # 5. Recent Logs
                cursor.execute("SELECT id, dest_name, device_id, status, ip, start_time, end_time, distance_m FROM tasks_log ORDER BY id DESC LIMIT 200")
                recent_logs = cursor.fetchall()

                # 6. LTE Usage
                cursor.execute("SELECT modem_name, init_upload, init_download, now_upload, now_download, updated_at FROM lte_data_usage WHERE work_date = %s ORDER BY modem_name ASC", (kst_date,))
                lte_usage = cursor.fetchall()
                
            return {
                "summary": {"total_target": total_target, "success": success_cnt, "fail": fail_cnt, "remain": max(0, total_target - success_cnt)},
                "system": system_status, "devices": devices_list, "destinations": dest_list, "logs": recent_logs, "lte": lte_usage
            }
        except Exception as e:
            print(f"Admin Summary Error: {e}")
            return JSONResponse(status_code=500, content={"error": str(e)})

    @app.get("/api/v1/admin/history/device/{device_id}")
    async def get_device_history(device_id: str):
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT dest_name, status, DATE_FORMAT(start_time, '%H:%i') as time, 
                           TIMESTAMPDIFF(MINUTE, start_time, COALESCE(end_time, NOW())) as duration
                    FROM tasks_log WHERE device_id = %s AND work_date = CURDATE() ORDER BY start_time DESC LIMIT 50
                """, (device_id,))
                return cursor.fetchall()
        except Exception as e: raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/admin/history/dest/{dest_id}")
    async def get_dest_history(dest_id: str):
        try:
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT work_date as date, success_cnt as success, fail_cnt as fail, last_dist_m as dist
                    FROM daily_progress WHERE dest_id = %s ORDER BY work_date DESC LIMIT 30
                """, (dest_id,))
                return cursor.fetchall()
        except Exception as e: raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/v1/admin/dest/update")
    async def update_destination(data: dict):
        # Using dict instead of pydantic model for simplicity in this registration helper
        dest_id = data.get("dest_id")
        status = data.get("status")
        limit = data.get("limit")
        try:
            with get_db_cursor() as cursor:
                if status: cursor.execute("UPDATE raw_slots SET status = %s WHERE dest_id = %s", (status, dest_id))
                if limit is not None: cursor.execute("UPDATE raw_slots SET work_count = %s WHERE dest_id = %s AND status='on'", (limit, dest_id))
            return {"status": "ok"}
        except Exception as e: raise HTTPException(status_code=500, detail=str(e))
