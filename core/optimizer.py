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
                    new_min = max(100, best_dist_m - 200)
                
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
        """가시거리 확보 실패: 여전히 케어 모드 유지하되 점검 시간 및 최단거리만 업데이트"""
        is_competitive = bool(re.search(r'누수|청소|하수구|변기|이사|싱크대|뚫음', name))
        dist_min = 10 if is_competitive else 100
        dist_max = 100 if is_competitive else 300
        
        conn = pymysql.connect(**DB_CONFIG, autocommit=True)
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE places 
                    SET check_status = 'FAIL', 
                        dist_min_m = %s,
                        dist_max_m = %s,
                        last_optimized_at = %s 
                    WHERE dest_id = %s
                """, (dist_min, dist_max, get_kst_now(), dest_id))
                print(f"  [STILL-FAILED] {dest_id}: Not found even at 1km. Narrowed range to {dist_min}m ~ {dist_max}m.")
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

        # 2. 최근 24시간 내 클라이언트 실패 이력 존재 여부 확인
        conn = pymysql.connect(**DB_CONFIG)
        has_client_failure = False
        try:
            with conn.cursor() as cursor:
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
        except Exception as e:
            print(f"  [!] Error checking fail history: {e}")
        finally:
            conn.close()
            
        print(f"  -> competitive: {is_competitive}, has_client_failure: {has_client_failure}")

        # 3. 탐색 대상 범위 결정 (가장 가까운 거리부터 먼 거리순으로 점진 테스트)
        if is_competitive:
            if has_client_failure:
                # 경쟁 카테고리 & 실패 발생 시 -> 가장 안전한 단거리 범위로 제한
                test_ranges = [300, 500, 800]
            else:
                # 경쟁 카테고리 -> 최대 3000m 까지만 탐색 제한
                test_ranges = [300, 500, 800, 1500, 3000]
        else:
            if has_client_failure:
                # 일반 카테고리 & 실패 발생 -> 최대 3000m 까지만 탐색 제한
                test_ranges = [300, 500, 800, 1500, 3000]
            else:
                # 일반 카테고리 정상 상태 -> 최대 10000m 까지 탐색 허용
                test_ranges = [300, 500, 800, 1500, 3000, 5000, 7000, 10000]

        # 4. 키워드별 가시거리 독립적 탐색 (모든 활성 키워드에 대해 안전하게 도달 가능한 가시거리를 확보하기 위함)
        keyword_best_distances = []
        any_keyword_succeeded = False
        
        for kw in keywords[:2]: # 상위 2개 키워드만 테스트
            best_dist_for_kw = None
            print(f"  -> Probing keyword: '{kw}'")
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
                
                # 가시 순위 기준을 만족하지 못하면 해당 키워드의 탐색 중단
                if not found_at_this_dist:
                    print(f"    Not found or unstable at {dist_m}m. Stopping probe for '{kw}'.")
                    break
            
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
