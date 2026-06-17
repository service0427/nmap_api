import os
import sys

# Path adjustment for standalone execution
if __name__ == "__main__" or "core" not in sys.modules:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import random
import secrets
import uuid
import hashlib
import time
from collections import OrderedDict
from urllib.parse import urlencode, quote
import hmac
import base64
from curl_cffi import requests as requests_cffi

from core.config import Config

from datetime import datetime, timedelta, timezone

def get_kst_now():
    """Returns the current time in KST (UTC+9)."""
    return datetime.now(timezone(timedelta(hours=9)))

def get_kst_date():
    """Returns the current date in KST (UTC+9)."""
    return get_kst_now().date()

class NaverGeoValidator:
    def __init__(self):
        self.session = requests_cffi.Session(impersonate="chrome110")
        self.hmac_key = Config.get_hmac_key()
        self.app_version = "6.5.2.1"
        self.user_agent = f"NaverMap/{self.app_version} (Android 13; SM-G998N)"

    def _generate_hmac(self, url):
        timestamp_ms = int(time.time() * 1000)
        msgpad = str(timestamp_ms)
        message = (url[:255] + msgpad).encode('utf-8')
        h = hmac.new(self.hmac_key, message, hashlib.sha1)
        return msgpad, base64.b64encode(h.digest()).decode('utf-8')

    def is_land(self, lat: float, lng: float):
        """Checks land validity with strict 3s timeout and safe fallback."""
        base_url = "https://apis.naver.com/mapmobileapps/maps-atlas/reversegeocoding"
        params = OrderedDict([
            ("output", "json"), ("request", "coordsToaddr"),
            ("caller", f"android_NaverMap_{self.app_version}"),
            ("orders", "admcode"), ("sourcecrs", "epsg:4326"),
            ("version", "1.0"), ("coords", f"{lng},{lat}"), ("reqlanguage", "ko")
        ])
        temp_url = base_url + "?" + urlencode(params, quote_via=quote)
        msgpad, md = self._generate_hmac(temp_url)
        params['msgpad'], params['md'] = msgpad, md
        final_url = base_url + "?" + urlencode(params, quote_via=quote)
        
        try:
            resp = self.session.get(final_url, headers={"user-agent": self.user_agent}, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status", {}).get("code") == 0
            return True 
        except:
            return True 

def generate_spoofed_identity():
    ssaid = secrets.token_hex(8)
    ni = hashlib.md5(ssaid.encode()).hexdigest()
    token = ''.join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(16))
    return {
        "ssaid": ssaid,
        "adid": str(uuid.uuid4()),
        "idfv": str(uuid.uuid4()),
        "ni": ni,
        "token": token
    }

geo_validator = NaverGeoValidator()

def calculate_gps_and_speed(lat1_deg, lng1_deg, min_dist_m, max_dist_m, min_arr_m, max_arr_m, fixed_arrival_s=None):
    """
    Great Circle Navigation 공식을 사용하여 정밀한 목적지 좌표를 계산합니다.
    (대권 항법: 지구 곡률을 고려한 정밀 이동)
    """
    R = 6371000.0 # 지구 반지름 (미터)
    
    # 1. 도(Degree) 단위를 라디안(Radian)으로 변환
    lat1 = math.radians(lat1_deg)
    lng1 = math.radians(lng1_deg)
    
    last_coords = (lat1_deg, lng1_deg, 0)
    
    # 2. 랜덤 좌표 및 거리 생성 (최대 5회 시도하여 육지 확인)
    for _ in range(5):
        # 이동 거리 (d) 랜덤 결정
        d = math.sqrt(random.random() * (max_dist_m**2 - min_dist_m**2) + min_dist_m**2)
        # 방위각 (bearing) 랜덤 결정 (0 ~ 360도)
        bearing = random.uniform(0, 2 * math.pi)
        
        # 3. 대권 항법 공식 적용
        # new_lat = arcsin(sin(lat1)*cos(d/R) + cos(lat1)*sin(d/R)*cos(bearing))
        lat2 = math.asin(math.sin(lat1) * math.cos(d/R) + 
                         math.cos(lat1) * math.sin(d/R) * math.cos(bearing))
        
        # new_lng = lng1 + atan2(sin(bearing)*sin(d/R)*cos(lat1), cos(d/R)-sin(lat1)*sin(lat2))
        lng2 = lng1 + math.atan2(math.sin(bearing) * math.sin(d/R) * math.cos(lat1),
                                 math.cos(d/R) - math.sin(lat1) * math.sin(lat2))
        
        # 다시 도(Degree) 단위로 변환
        res_lat = round(math.degrees(lat2), 8)
        res_lng = round(math.degrees(lng2), 8)
        
        last_coords = (res_lat, res_lng, round(d, 2))
        
        # 육지 검증 통과 시 루프 종료
        if geo_validator.is_land(res_lat, res_lng):
            break
            
    # 4. 도착 시간 설정 (사용자 지정값(초) 우선)
    res_lat, res_lng, final_dist = last_coords
    
    if fixed_arrival_s is not None and fixed_arrival_s > 0:
        arrival_sec = fixed_arrival_s
    else:
        arrival_sec = random.randint(min_arr_m * 60, max_arr_m * 60)
        
    # 5. 속도 계산 (km/h = (m / 1000) / (sec / 3600))
    speed_kmh = round((final_dist / 1000.0) / (arrival_sec / 3600.0), 2)
    
    return res_lat, res_lng, final_dist, speed_kmh
