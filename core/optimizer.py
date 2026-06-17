import sys
import os
import pymysql
import random
import time
import asyncio
import threading
from datetime import datetime

# Path adjustment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.scraper import NaverPlaceScraper
from core.config import Config
from core.utils import get_kst_now, calculate_gps_and_speed

# Config
DB_CONFIG = Config.get_db_config()

class VisibilityOptimizer:
    def __init__(self):
        self.scraper = NaverPlaceScraper()
        self.max_threads = 3 # 네이버 차단 방지를 위해 적정 수준 유지
        
    def get_targets(self):
        conn = pymysql.connect(**DB_CONFIG)
        try:
            with conn.cursor() as cursor:
                # 1. is_optimizer = 1 인 대상을 우선순위 높은 순으로 가져옴
                query = """
                    SELECT * FROM places 
                    WHERE is_optimizer = 1 
                    ORDER BY optimization_priority DESC, last_optimized_at ASC
                    LIMIT 20
                """
                cursor.execute(query)
                return cursor.fetchall()
        finally:
            conn.close()

    def update_place_verified(self, dest_id, best_dist_m):
        """졸업 성공: 가시거리 확정 및 optimizer 모드 해제"""
        conn = pymysql.connect(**DB_CONFIG, autocommit=True)
        try:
            with conn.cursor() as cursor:
                new_max = best_dist_m
                new_min = max(500, best_dist_m - 2000) # Max에서 2km 안쪽 범위를 기본값으로
                
                cursor.execute("""
                    UPDATE places 
                    SET dist_max_m = %s, 
                        dist_min_m = %s,
                        is_optimizer = 0,
                        check_status = 'VERIFIED',
                        last_optimized_at = %s,
                        optimization_priority = 0
                    WHERE dest_id = %s
                """, (new_max, new_min, get_kst_now(), dest_id))
                print(f"  [GRADUATED] {dest_id}: Range {new_min}m ~ {new_max}m")
        finally:
            conn.close()

    def update_place_failed(self, dest_id):
        """가시거리 확보 실패: 여전히 케어 모드 유지하되 점검 시간만 업데이트"""
        conn = pymysql.connect(**DB_CONFIG, autocommit=True)
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE places 
                    SET check_status = 'FAIL', 
                        last_optimized_at = %s 
                    WHERE dest_id = %s
                """, (get_kst_now(), dest_id))
                print(f"  [STILL-FAILED] {dest_id}: Not found even at 1km.")
        finally:
            conn.close()

    def probe_place(self, place):
        dest_id = place['dest_id']
        name = place['name']
        print(f"[*] Optimizing Visibility for: {name} ({dest_id})")
        
        # 10km -> 7km -> 5km -> 3km -> 1.5km -> 0.8km 순차 탐색
        test_ranges = [10000, 7000, 5000, 3000, 1500, 800]
        
        # 키워드 가져오기
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("SELECT keyword FROM place_keywords WHERE dest_id = %s AND status = 'on'", (dest_id,))
            keywords = [r['keyword'] for r in cursor.fetchall()]
        conn.close()
        
        if not keywords: keywords = [name]
        
        best_found_dist = None
        
        for dist_m in test_ranges:
            found_at_this_dist = False
            for kw in keywords[:2]: # 상위 2개 키워드만 테스트
                # 해당 거리의 랜덤 좌표 2곳 테스트
                for _ in range(2):
                    # calculate_gps_and_speed를 활용해 좌표 생성
                    s_lat, s_lng, real_d, _ = calculate_gps_and_speed(float(place['lat']), float(place['lng']), dist_m - 100, dist_m, 0, 0, fixed_arrival_s=600)
                    
                    try:
                        res = self.scraper._mobile_search(kw, lat=str(s_lat), lng=str(s_lng), timeout=5)
                        places = res.get("place", [])
                        
                        # Top 8 이내 진입 확인
                        idx = next((i for i, p in enumerate(places[:8]) if str(p.get('id')) == str(dest_id)), -1)
                        if idx != -1:
                            print(f"  -> Found at {dist_m}m (Rank {idx+1}) with keyword '{kw}'")
                            best_found_dist = dist_m
                            found_at_this_dist = True
                            break
                        
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"  [!] Search Error: {e}")
                        time.sleep(1)
                
                if found_at_this_dist: break
            
            if found_at_this_dist:
                # 가시거리 확보됨 -> 더 좁은 범위는 안 봐도 됨 (Max를 찾기 위함이므로)
                break
        
        if best_found_dist:
            self.update_place_verified(dest_id, best_found_dist)
        else:
            self.update_place_failed(dest_id)

    def run(self):
        print(f"=== Visibility Management Tool Started: {get_kst_now()} ===")
        targets = self.get_targets()
        if not targets:
            print("No targets in Care Mode (is_optimizer=1).")
            return

        print(f"Found {len(targets)} targets to optimize.")
        for t in targets:
            self.probe_place(t)
            time.sleep(1) # IP 차단 방지 간격

if __name__ == "__main__":
    optimizer = VisibilityOptimizer()
    optimizer.run()
