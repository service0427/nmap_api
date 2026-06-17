import os
import sys

# Path adjustment for standalone execution
if __name__ == "__main__" or "core" not in sys.modules:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
import re
import urllib3
import hmac
import hashlib
import base64
import time
import uuid
from urllib.parse import urlencode, quote
from collections import OrderedDict
from curl_cffi import requests as requests_cffi

from core.config import Config

class NaverPlaceScraper:
    def __init__(self):
        self.session = requests_cffi.Session(impersonate="chrome110")
        self.hmac_key = Config.get_hmac_key()
        self.app_version = "6.5.2.1"
        self.user_agent = f"NaverMap/{self.app_version} (Android 13; SM-G998N)"

    def parse_id(self, input_value):
        """URL 또는 문자열에서 숫자 ID만 추출"""
        input_value = input_value.strip()
        if not input_value: return None
        match = re.search(r'(\d+)', input_value.split('/')[-1]) or re.search(r'(\d+)', input_value)
        return match.group(1) if match else None

    def _generate_hmac(self, url):
        """네이버 지도 모바일 API용 HMAC 서명 생성"""
        timestamp_ms = int(time.time() * 1000)
        msgpad = str(timestamp_ms)
        message = (url[:255] + msgpad).encode('utf-8')
        h = hmac.new(self.hmac_key, message, hashlib.sha1)
        return msgpad, base64.b64encode(h.digest()).decode('utf-8')

    def _mobile_search(self, query, lat="37.5665", lng="126.9780", timeout=10):
        """HMAC 서명을 포함한 모바일 앱 방식 검색 API 호출"""
        base_url = "https://apis.naver.com/mapmobileapps/maps-search/instantSearchV2"
        params = OrderedDict([
            ("screenid", "SCH.instant"),
            ("caller", f"android_NaverMap_{self.app_version}"),
            ("types", "place,address,bus"),
            ("onlyBookable", "false"),
            ("query", query),
            ("lang", "ko"),
            ("coords", f"{lat},{lng}")
        ])
        
        temp_url = base_url + "?" + urlencode(params, quote_via=quote)
        msgpad, md = self._generate_hmac(temp_url)
        params['msgpad'] = msgpad
        params['md'] = md
        
        final_url = base_url + "?" + urlencode(params, quote_via=quote)
        headers = {
            "x-adid": str(uuid.uuid4()),
            "referer": "client://NaverMap",
            "user-agent": self.user_agent,
            "uuid": uuid.uuid4().hex
        }
        
        try:
            resp = self.session.get(final_url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            return {"error": resp.status_code}
        except Exception as e:
            return {"error": str(e)}

    def fetch_place_info(self, place_id):
        """
        고유 알고리즘: POI 기본정보 -> 1차 상호검색 -> (실패시) 주소 GPS 고정 -> 2차 정밀검색
        """
        poi_url = f"https://map.naver.com/p/api/place/directionsPOI/{place_id}"
        poi_headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://map.naver.com/"}
        
        try:
            res_poi = requests.get(poi_url, headers=poi_headers, timeout=10)
            if res_poi.status_code != 200:
                return {"error": "poi_fail", "message": f"POI API 오류 ({res_poi.status_code})"}
            
            poi_data = res_poi.json().get("data", {}).get("placeDetail", {})
            name = poi_data.get("name")
            addr = poi_data.get("address", {}).get("address")
            
            if not name:
                return {"error": "no_name", "message": "장소 이름을 찾을 수 없음"}

            search_res = self._mobile_search(name)
            places = search_res.get("place", [])
            match = next((p for p in places if p.get("id") == place_id), None)

            if not match and addr:
                addr_res = self._mobile_search(addr)
                addr_list = addr_res.get("address", [])
                if addr_list:
                    anchor_lat = addr_list[0]['y']
                    anchor_lng = addr_list[0]['x']
                    search_res_v2 = self._mobile_search(name, lat=anchor_lat, lng=anchor_lng)
                    places_v2 = search_res_v2.get("place", [])
                    match = next((p for p in places_v2 if p.get("id") == place_id), None)

            # 최종 데이터 추출
            if match:
                # shortAddress는 리스트 형태 (예: ["경기", "수원시", ...])
                short_addr_list = match.get("shortAddress", [])
                if isinstance(short_addr_list, list) and short_addr_list:
                    # 실제 앱 검색 결과와 동일한 shortAddress 기반 주소
                    final_addr = " ".join(short_addr_list)
                else:
                    # 백업: roadAddress 또는 jibunAddress
                    final_addr = match.get("roadAddress") or match.get("jibunAddress")

                return {
                    "id": match.get("id"),
                    "name": match.get("title"),
                    "address": final_addr, # 이것이 shortAddress 기반 주소
                    "lng": float(match.get("x") or 0),
                    "lat": float(match.get("y") or 0)
                }
            else:
                return {"error": "not_found", "message": "검색 결과 매칭 실패"}

        except Exception as e:
            return {"error": "exception", "message": str(e)}

    def _clean_address(self, address):
        """주소의 첫 번째 토막(도 단위) 제거"""
        if not address: return address
        parts = address.strip().split(' ')
        if len(parts) > 1:
            return ' '.join(parts[1:]).strip()
        return address
