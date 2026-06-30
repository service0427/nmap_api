import sys
import os
import pymysql
import random
import time
import asyncio
import threading
import re
from datetime import datetime

# Path adjustment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.scraper import NaverPlaceScraper
from core.config import Config
from core.utils import get_kst_now, get_kst_date, calculate_gps_and_speed

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
                if best_dist_m >= 1500:
                    new_min = max(500, best_dist_m - 2000)
                elif best_dist_m >= 800:
                    new_min = max(300, best_dist_m - 500)
                else:
                    new_min = max(300, best_dist_m - 200)
                
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

    def update_place_failed(self, dest_id, name):
        """가시거리 확보 실패: 점진적으로 가시거리를 좁힘 (최소 100m ~ 300m 제한)"""
        conn = pymysql.connect(**DB_CONFIG, autocommit=True)
        try:
            with conn.cursor() as cursor:
                # 1. 현재 설정된 거리 확인
                cursor.execute("SELECT dist_min_m, dist_max_m FROM places WHERE dest_id = %s", (dest_id,))
                row = cursor.fetchone()
                
                curr_min = 1000
                curr_max = 3000
                if row:
                    curr_min = int(row['dist_min_m']) if row['dist_min_m'] is not None else 1000
                    curr_max = int(row['dist_max_m']) if row['dist_max_m'] is not None else 3000
                
                # 2. 단계적으로 가시거리 좁히기 (10m 주행 방지, 내비게이션 최소 주행거리 확보)
                if curr_max > 5000:
                    new_max = 3000
                    new_min = 1000
                elif curr_max > 3000:
                    new_max = 1500
                    new_min = 500
                elif curr_max > 1500:
                    new_max = 800
                    new_min = 300
                elif curr_max > 800:
                    new_max = 500
                    new_min = 300
                else:
                    new_max = 300
                    new_min = 300
                    
                cursor.execute("""
                    UPDATE places 
                    SET check_status = 'FAIL', 
                        dist_min_m = %s,
                        dist_max_m = %s,
                        last_optimized_at = %s 
                    WHERE dest_id = %s
                """, (new_min, new_max, get_kst_now(), dest_id))
                print(f"  [STILL-FAILED] {dest_id}: Gradual shrink applied. Range narrowed from {curr_min}m~{curr_max}m to {new_min}m~{new_max}m.")
        finally:
            conn.close()

    def probe_place(self, place):
        dest_id = place['dest_id']
        name = place['name']
        print(f"[*] Optimizing Visibility for: {name} ({dest_id})")
        
        # 키워드 가져오기
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("SELECT keyword FROM place_keywords WHERE dest_id = %s AND status = 'on'", (dest_id,))
            keywords = [r['keyword'] for r in cursor.fetchall()]
            
            # place_keywords가 비어있는 경우 raw_slots의 search_keyword를 2차로 조회하여 지역 키워드 누락 방지
            if not keywords:
                cursor.execute("""
                    SELECT DISTINCT search_keyword 
                    FROM raw_slots 
                    WHERE dest_id = %s 
                      AND status = 'on' 
                      AND is_deleted = 0 
                      AND search_keyword IS NOT NULL 
                      AND search_keyword != ''
                """, (dest_id,))
                keywords = [r['search_keyword'] for r in cursor.fetchall()]
        conn.close()
        
        if not keywords: keywords = [name]

        # 1. 경쟁이 심한 카테고리 여부 판단
        is_competitive = False
        competitive_pattern = r'누수|청소|하수구|변기|이사|싱크대|뚫음'
        if re.search(competitive_pattern, name):
            is_competitive = True
        else:
            for kw in keywords:
                if re.search(competitive_pattern, kw):
                    is_competitive = True
                    break

        # 2. 최근 24시간 내 클라이언트 실패 이력 존재 여부 및 전날 최종 목적지 거리(last_dist_m) 확인
        conn = pymysql.connect(**DB_CONFIG)
        has_client_failure = False
        start_dist = 1000
        try:
            with conn.cursor() as cursor:
                # 최근 24시간 실패 이력 확인
                cursor.execute("""
                    SELECT SUM(fail_cnt) as total_fail 
                    FROM daily_progress 
                    WHERE dest_id = %s AND (work_date = %s OR last_fail_at >= %s - INTERVAL 24 HOUR)
                """, (dest_id, get_kst_date(), get_kst_now()))
                row = cursor.fetchone()
                if row:
                    val = row['total_fail'] if isinstance(row, dict) else row[0]
                    if val and int(val) >= 1:
                        has_client_failure = True
                        
                # 전날 마지막 최종 목적지(last_dist_m) 확인
                cursor.execute("""
                    SELECT last_dist_m 
                    FROM daily_progress 
                    WHERE dest_id = %s AND work_date < %s AND success_cnt > 0
                    ORDER BY work_date DESC LIMIT 1
                """, (dest_id, get_kst_date()))
                prev_row = cursor.fetchone()
                if prev_row and prev_row['last_dist_m']:
                    start_dist = int(prev_row['last_dist_m'])
                else:
                    start_dist = int(place['dist_max_m']) if place.get('dist_max_m') else 1000
        except Exception as e:
            print(f"  [!] Error checking history/last_dist_m: {e}")
        finally:
            conn.close()
            
        print(f"  -> Has client failure: {has_client_failure}, Start Distance: {start_dist}m")

        # 3. 100m씩 줄이며 최대 5번(500m 감산) 테스트 범위(ranges) 결정 (최소 300m 보장)
        test_ranges = []
        curr_d = start_dist
        for i in range(5):
            test_ranges.append(curr_d)
            curr_d -= 100
            if curr_d < 300:
                break
                
        # 4. 키워드별 가시거리 독립적 탐색
        keyword_best_distances = []
        any_keyword_succeeded = False
        
        for kw in keywords[:2]: # 상위 2개 키워드만 테스트
            best_dist_for_kw = None
            print(f"  -> Probing keyword: '{kw}' (Test Ranges: {test_ranges})")
            for dist_m in test_ranges:
                found_at_this_dist = False
                for _ in range(2):
                    s_lat, s_lng, real_d, _ = calculate_gps_and_speed(float(place['lat']), float(place['lng']), dist_m - 100, dist_m, 0, 0, fixed_arrival_s=600)
                    
                    try:
                        res = self.scraper._mobile_search(kw, lat=str(s_lat), lng=str(s_lng), timeout=5)
                        places = res.get("place", [])
                        
                        # 전체 검색 결과 대상 순위 체크
                        idx = next((i for i, p in enumerate(places) if str(p.get('id')) == str(dest_id)), -1)
                        if idx != -1:
                            rank = idx + 1
                            
                            # 거리에 따른 안정적 가시권 보증 순위 기준 (먼 거리일수록 엄격하게 검증)
                            if dist_m >= 5000:
                                max_allowed_rank = 3
                            elif dist_m >= 1500:
                                max_allowed_rank = 5
                            else:
                                max_allowed_rank = 8
                                
                            if rank <= max_allowed_rank:
                                print(f"    Found at {dist_m}m (Rank {rank}, Max Allowed: {max_allowed_rank})")
                                best_dist_for_kw = dist_m
                                found_at_this_dist = True
                                break
                        
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"    [!] Search Error: {e}")
                        time.sleep(1)
                
                # 8등 이내에 들어올 때까지 단계별로 진행 (순위 노출 성공 시 즉시 해당 거리를 채택하고 루프 중단)
                if found_at_this_dist:
                    break
                else:
                    print(f"    Not found or unstable at {dist_m}m. Stepping down 100m...")
            
            if best_dist_for_kw:
                keyword_best_distances.append(best_dist_for_kw)
                any_keyword_succeeded = True
            else:
                # 하나라도 성공한 키워드가 있으면, 실패한 키워드의 안전거리는 최소 300m로 대입하여 전체 처리가 중단되는 것을 방지
                keyword_best_distances.append(300)

        # 5. 모든 키워드가 공통적으로 가시성을 확보하는 최솟값을 최종 졸업 거리로 결정
        if any_keyword_succeeded:
            best_found_dist = min(keyword_best_distances)
        else:
            best_found_dist = None
        
        if best_found_dist:
            self.update_place_verified(dest_id, best_found_dist)
        else:
            self.update_place_failed(dest_id, name)

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
