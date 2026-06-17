# Gemini Operational Instructions - Nmap API

## Server Roles
- **Local (Dev)**:  - Development environment. Database: local MySQL.
- **AWS (Prod API)**:  (api.qewr.link) - Main API server. 
    - **Stack**: Nginx (Reverse Proxy) + FastAPI (PM2).
    - **Capacity**: Optimized for hundreds of concurrent client connections.
- **AWS (Prod Web)**:  (web.qewr.link) - Monitoring & Keyword Management.
    - **Stack**: Apache (Port 80).
    - **Access**: Admin use only, lightweight server.

## Development Standards
- **Database**: Strictly use  for both dev and production.
- **Prefixes**: Do NOT use prefixes like  or . Use clean table names.
- **Table Structure**: Consolidated  and  into a single  table for efficiency.
- **Methodology**: 
    - Sync -> Aggregate -> Optimize workflow.
    - Always validate GPS coordinates for  before dispatch.

## Architecture Context
- **Web Server (3.39.228.30)**: Reserved for low-load monitoring and management UI.
- **Separation of Concerns**: Web is decoupled from API to preserve API server resources for high-frequency tasks.
- **RDS Connectivity**: Web server connects to the same RDS as the API server for consistent data management.
- **Traffic Management**: Nginx is used for the API server to handle high-volume client traffic (hundreds of connections), while Apache is sufficient for the internal monitoring web server.

## Critical Paths
- : Must maintain identity spoofing logic.
- **IP Handling**: Task allocation is priority; initial IP is irrelevant. Post-processing () handles the swapped IP (airplane mode).
- : Adjust  only after verifying impact on search visibility.
- : Preserve  as the primary address source.

## Git Protocol
- Ignore , , and .
- Keep  updated for deployment portability.

## Operational Standards
- **Timezone Policy (Strict)**: RDS system time is NOT in KST. All database inputs (NOW, CURDATE equivalent) MUST be calculated in Python using  or  to ensure 100% KST consistency. NEVER use SQL functions like  or  for business-critical timestamps.
- **PM2 Logs**: Always use  instead of  when checking logs (e.g., [1m[90m[TAILING] Tailing last 50 lines for [nmap-api] process (change the value with --lines option)[39m[22m
[90m/home/tech/.pm2/logs/nmap-api-error.log last 50 lines:[39m
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119466', 'applied_speed': 66.6, 'status': 'DRIVING', 'remaining_dist': 6.214672625520292}}] | Body: {"task_id": "119466", "applied_speed": 66.6, "status": "DRIVING", "remaining_dist": 6.214672625520292}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119450', 'applied_speed': 113.3, 'status': 'DRIVING', 'remaining_dist': 10.735326296197103}}] | Body: {"task_id": "119450", "applied_speed": 113.3, "status": "DRIVING", "remaining_dist": 10.735326296197103}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119467', 'applied_speed': 17.3, 'status': 'DRIVING', 'remaining_dist': 1.1100047790008534}}] | Body: {"task_id": "119467", "applied_speed": 17.3, "status": "DRIVING", "remaining_dist": 1.1100047790008534}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119455', 'applied_speed': 150.9, 'status': 'DRIVING', 'remaining_dist': 17.564019091581365}}] | Body: {"task_id": "119455", "applied_speed": 150.9, "status": "DRIVING", "remaining_dist": 17.564019091581365}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119465', 'applied_speed': 50.4, 'status': 'DRIVING', 'remaining_dist': 6.580081313037999}}] | Body: {"task_id": "119465", "applied_speed": 50.4, "status": "DRIVING", "remaining_dist": 6.580081313037999}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119477', 'applied_speed': 57.4, 'status': 'DRIVING', 'remaining_dist': 7.625769408276233}}] | Body: {"task_id": "119477", "applied_speed": 57.4, "status": "DRIVING", "remaining_dist": 7.625769408276233}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119445', 'applied_speed': 41.3, 'status': 'DRIVING', 'remaining_dist': 4.731271526487629}}] | Body: {"task_id": "119445", "applied_speed": 41.3, "status": "DRIVING", "remaining_dist": 4.731271526487629}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119470', 'applied_speed': 16.8, 'status': 'DRIVING', 'remaining_dist': 1.363322361047198}}] | Body: {"task_id": "119470", "applied_speed": 16.8, "status": "DRIVING", "remaining_dist": 1.363322361047198}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119471', 'applied_speed': 82.8, 'status': 'DRIVING', 'remaining_dist': 9.86792252015445}}] | Body: {"task_id": "119471", "applied_speed": 82.8, "status": "DRIVING", "remaining_dist": 9.86792252015445}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119478', 'applied_speed': 77.5, 'status': 'DRIVING', 'remaining_dist': 10.20694162182143}}] | Body: {"task_id": "119478", "applied_speed": 77.5, "status": "DRIVING", "remaining_dist": 10.20694162182143}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119474', 'applied_speed': 18.2, 'status': 'DRIVING', 'remaining_dist': 1.109246532086412}}] | Body: {"task_id": "119474", "applied_speed": 18.2, "status": "DRIVING", "remaining_dist": 1.109246532086412}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119468', 'applied_speed': 35.6, 'status': 'DRIVING', 'remaining_dist': 3.486913362641562}}] | Body: {"task_id": "119468", "applied_speed": 35.6, "status": "DRIVING", "remaining_dist": 3.486913362641562}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119473', 'applied_speed': 39.8, 'status': 'DRIVING', 'remaining_dist': 4.6099303357393095}}] | Body: {"task_id": "119473", "applied_speed": 39.8, "status": "DRIVING", "remaining_dist": 4.6099303357393095}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119485', 'applied_speed': 70.4, 'status': 'DRIVING', 'remaining_dist': 7.115905456020836}}] | Body: {"task_id": "119485", "applied_speed": 70.4, "status": "DRIVING", "remaining_dist": 7.115905456020836}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119476', 'applied_speed': 219.0, 'status': 'DRIVING', 'remaining_dist': 24.15612520897228}}] | Body: {"task_id": "119476", "applied_speed": 219.0, "status": "DRIVING", "remaining_dist": 24.15612520897228}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119484', 'applied_speed': 101.8, 'status': 'DRIVING', 'remaining_dist': 12.046259603918733}}] | Body: {"task_id": "119484", "applied_speed": 101.8, "status": "DRIVING", "remaining_dist": 12.046259603918733}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119457', 'applied_speed': 119.9, 'status': 'DRIVING', 'remaining_dist': 12.558664230514404}}] | Body: {"task_id": "119457", "applied_speed": 119.9, "status": "DRIVING", "remaining_dist": 12.558664230514404}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119452', 'applied_speed': 66.7, 'status': 'DRIVING', 'remaining_dist': 7.819693914913667}}] | Body: {"task_id": "119452", "applied_speed": 66.7, "status": "DRIVING", "remaining_dist": 7.819693914913667}
[31m6|nmap-api | [39m[Validation Error] Path: /api/v1/update_status | Detail: [{'type': 'missing', 'loc': ('body', 'device_id'), 'msg': 'Field required', 'input': {'task_id': '119481', 'applied_speed': 80.5, 'status': 'DRIVING', 'remaining_dist': 9.476283271375435}}] | Body: {"task_id": "119481", "applied_speed": 80.5, "status": "DRIVING", "remaining_dist": 9.476283271375435}
[31m6|nmap-api | [39mINFO:     Shutting down
[31m6|nmap-api | [39mINFO:     Waiting for application shutdown.
[31m6|nmap-api | [39mINFO:     Application shutdown complete.
[31m6|nmap-api | [39mINFO:     Finished server process [3213928]
[31m6|nmap-api | [39m/home/tech/aws/nmap_api/api_server.py:240: DeprecationWarning: 
[31m6|nmap-api | [39m        on_event is deprecated, use lifespan event handlers instead.
[31m6|nmap-api | [39m
[31m6|nmap-api | [39m        Read more about it in the
[31m6|nmap-api | [39m        [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
[31m6|nmap-api | [39m        
[31m6|nmap-api | [39m  @app.on_event("startup")
[31m6|nmap-api | [39mINFO:     Started server process [3214169]
[31m6|nmap-api | [39mINFO:     Waiting for application startup.
[31m6|nmap-api | [39mINFO:     Application startup complete.
[31m6|nmap-api | [39mINFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
[31m6|nmap-api | [39mINFO:     Shutting down
[31m6|nmap-api | [39mINFO:     Waiting for connections to close. (CTRL+C to force quit)
[31m6|nmap-api | [39mINFO:     Waiting for application shutdown.
[31m6|nmap-api | [39mINFO:     Application shutdown complete.
[31m6|nmap-api | [39mINFO:     Finished server process [3214169]
[31m6|nmap-api | [39m/home/tech/aws/nmap_api/api_server.py:240: DeprecationWarning: 
[31m6|nmap-api | [39m        on_event is deprecated, use lifespan event handlers instead.
[31m6|nmap-api | [39m
[31m6|nmap-api | [39m        Read more about it in the
[31m6|nmap-api | [39m        [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
[31m6|nmap-api | [39m        
[31m6|nmap-api | [39m  @app.on_event("startup")
[31m6|nmap-api | [39mINFO:     Started server process [3226350]
[31m6|nmap-api | [39mINFO:     Waiting for application startup.
[31m6|nmap-api | [39mINFO:     Application startup complete.
[31m6|nmap-api | [39mINFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

[90m/home/tech/.pm2/logs/nmap-api-out.log last 50 lines:[39m
[32m6|nmap-api | [39mINFO:     183.102.240.198:50568 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39m[*] Gradual Inspection: 하수구막힘 (Baseline: 3614m)
[32m6|nmap-api | [39mINFO:     110.70.59.118:14656 - "POST /api/v1/request_task HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     220.78.250.43:49526 - "POST /api/v1/report_result HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:60194 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     110.70.59.118:61252 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:60196 - "POST /api/v1/report_result HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:60210 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:60222 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     110.70.59.118:48548 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     222.100.154.79:32818 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     210.217.47.247:48102 - "POST /api/v1/request_task HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     221.154.248.237:54978 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     121.173.150.42:49362 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:53206 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     220.78.250.43:59826 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     221.165.105.146:42176 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:53212 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:53224 - "POST /api/v1/report_result HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     39.7.50.181:57509 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     121.173.150.125:38660 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     121.172.70.162:52436 - "POST /api/v1/request_task HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     121.173.150.125:38666 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     222.100.154.79:32826 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     183.102.240.198:54544 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.223.34.46:43712 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     110.70.59.118:56174 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     210.217.47.247:48106 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     220.126.156.104:50586 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     210.217.47.247:48108 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:53236 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     222.100.154.79:32828 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     220.126.156.104:50598 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     210.217.47.247:48122 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     183.102.240.198:54552 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:53250 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     220.126.156.104:50612 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     222.100.154.79:32842 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     210.217.47.247:48128 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     183.102.240.198:54562 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     220.126.156.104:50626 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:53262 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     222.100.154.79:32858 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     210.217.47.247:48138 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     220.78.250.43:59842 - "POST /api/v1/update_status HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     175.210.218.126:53278 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     183.102.240.198:54572 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     222.100.154.79:32864 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     183.102.240.198:54574 - "POST /api/v1/lte_usage HTTP/1.1" 200 OK
[32m6|nmap-api | [39mINFO:     121.172.70.162:52450 - "POST /api/v1/update_status HTTP/1.1" 200 OK).
- **Sync Code**: Use the  command defined in  to push local changes to AWS.
