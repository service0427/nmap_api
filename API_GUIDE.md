# 🚀 Nmap API Integration Guide (v1.2)

이 문서는 Nmap API 서버(`api.qewr.link`)와 연동하는 클라이언트를 위한 상세 가이드입니다. 클라이언트는 본 가이드의 응답 구조를 엄격히 준수해야 합니다.

---

## 📍 기본 정보
*   **Base URL**: `http://api.qewr.link` (또는 `http://15.165.243.244:8000`)
*   **Port**: `8000`
*   **Content-Type**: `application/json`
*   **Timezone**: 모든 시간은 **KST (한국 표준시)** 기준입니다.

---

## 1️⃣ 작업 할당 요청 (Request Task)
기기에 새로운 작업을 할당받습니다. 서버는 기기별 상태, IP 중복 여부, 업체 노출 순위(Optimizer)를 분석하여 최적의 작업을 반환합니다.

*   **Endpoint**: `POST /api/v1/request_task`
*   **Payload**:
    *   `device_id` (필수): 기기 고유 식별값 (예: `R3CN10BZ7PD`)
    *   `ip` (옵션): 현재 기기의 실 IP. (전달 시 동일 IP 중복 할당 방지 로직 작동)
    *   `site_id` (옵션): 특정 그룹 필터링 (예: `FSD`)
    *   `arrival_time` (옵션): 특정 주행 시간을 강제할 경우 사용 (초 단위)

### 성공 응답 (Status: "ok")
작업이 정상 할당되면 아래와 같이 상세 정보를 반환합니다. **특히 `identity`와 `start_pos` 정보를 기기 설정에 즉시 반영해야 합니다.**

```json
{
  "status": "ok",
  "task_id": 45678,
  "device_seq": 12,
  "destination": {
    "id": "12345678",
    "target_name": "카페 예시",
    "search_keyword": "강남역 맛집",
    "address": "서울특별시 강남구 ...",
    "lat": 37.123456,
    "lng": 127.123456
  },
  "start_pos": {
    "lat": 37.120000,
    "lng": 127.110000,
    "speed_kmh": 15.5,
    "dist_m": 850
  },
  "arrival_time": 300,
  "identity": {
    "original": { "ssaid": "...", "adid": "...", "idfv": "...", "ni": "...", "token": "..." },
    "spoofed": { "ssaid": "new-id-1", "adid": "new-id-2", "idfv": "new-id-3", "ni": "new-id-4", "token": "new-id-5" }
  }
}
```

*   **`search_keyword`**: 반드시 이 키워드로 검색을 수행해야 합니다.
*   **`start_pos`**: GPS 시뮬레이션의 시작점이며, `speed_kmh`는 권장 속도입니다.
*   **`arrival_time`**: 목표 주행 시간(초)입니다. 최소 300초(5분)가 보장됩니다.
*   **`identity.spoofed`**: 기기의 고유 식별값들을 이 값으로 변조(Identity Spoofing)한 후 작업을 진행해야 합니다.

---

## 2️⃣ 상태 업데이트 (Update Status)
작업 진행 중 주요 시점(IP 변경 완료, 주행 시작, 검색 완료 등)마다 서버에 상태를 보고합니다.

*   **Endpoint**: `POST /api/v1/update_status`
*   **Payload**:
    *   `task_id` (필수): 할당받은 작업 ID
    *   `device_id` (필수): 기기 ID
    *   `status` (필수): 현재 상태 (`RUNNING`, `ARRIVED`, `SEARCH_DONE`, `SUCCESS`, `FAIL` 등)
    *   `real_ip` (권장): 비행기 모드 스왑 후 변경된 실제 IP
    *   `drive_dist`: 현재까지 이동한 거리 (m)
    *   `drive_time`: 현재까지 소요된 시간 (s)
    *   `actual_address`: 검색 결과에서 실제 확인된 주소 (검증용)
    *   `error_msg`: 실패 시 상세 사유

### cURL 예시 (IP 스왑 및 주행 시작 보고)
```bash
curl -X POST "http://api.qewr.link/api/v1/update_status" \
     -H "Content-Type: application/json" \
     -d '{
       "task_id": 45678,
       "device_id": "R3CN10BZ7PD",
       "status": "RUNNING",
       "real_ip": "211.234.56.80",
       "drive_dist": 0,
       "drive_time": 0
     }'
```

---

## 3️⃣ 최종 결과 보고 (Report Result)
작업 종료 후 최종 결과를 보고합니다. `SUCCESS` 보고 시 통계에 즉시 반영됩니다.

*   **Endpoint**: `POST /api/v1/report_result`
*   **Payload**:
    *   `task_id`, `device_id`, `status` (`SUCCESS` 또는 `FAIL`)
    *   `drive_dist`: 최종 총 주행 거리 (m)
    *   `drive_time`: 최종 총 소요 시간 (s)
    *   `calc_speed`: 평균 이동 속도 (km/h)
    *   `message`: 작업 로그 또는 실패 사유

### cURL 예시
```bash
curl -X POST "http://api.qewr.link/api/v1/report_result" \
     -H "Content-Type: application/json" \
     -d '{
       "task_id": 45678,
       "device_id": "R3CN10BZ7PD",
       "status": "SUCCESS",
       "drive_dist": 855,
       "drive_time": 310,
       "calc_speed": 10.5,
       "message": "정상 도착 및 클릭 완료"
     }'
```

---

## ⚠️ 주요 에러 메시지 (`status: "error"`)

| 에러 메시지 | 의미 | 대응 방법 |
| :--- | :--- | :--- |
| `NO_TASK_AVAILABLE` | 할당 가능한 작업 물량이 없음 | 10~20분 후 재시도 또는 작업 종료 |
| `VISIBILITY_NOT_GUARANTEED` | 타겟 업체가 검색 결과(Top 8) 내에 없음 | 서버가 자동 최적화 중이므로 10분 후 재시도 |
| `UNAUTHORIZED_DEVICE` | 미등록 또는 사용 중지된 기기 | 관리자에게 기기 `status='on'` 확인 요청 |

---

## 4️⃣ LTE 데이터 사용량 보고 (LTE Data Usage)
모뎀의 실시간 데이터 사용량을 보고합니다. (10분 주기 권장)

*   **Endpoint**: `POST /api/v1/lte_usage`
*   **Payload**:
    *   `name`: 모뎀 이름 (예: `lte11`)
    *   `upload`: 누적 업로드 (Bytes)
    *   `download`: 누적 다운로드 (Bytes)

---

## 🩺 시스템 헬스체크
서버 생존 여부 확인: `GET /api/v1/health`
