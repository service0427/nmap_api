import os
import sys
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Path adjustment to access core and local modules
ADMIN_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ADMIN_DIR)

if ADMIN_DIR not in sys.path:
    sys.path.append(ADMIN_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# Import modular API endpoints
from api import summary, devices, destinations

app = FastAPI(title="Nmap Command Center PRO")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Sub-Routers
app.include_router(summary.router)
app.include_router(devices.router)
app.include_router(destinations.router)

# Page Endpoints for HTML5 History Routing
def get_no_cache_html_response():
    index_path = os.path.join(ADMIN_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return HTMLResponse(content=content, headers=headers)

@app.get("/", response_class=HTMLResponse)
async def serve_root():
    return get_no_cache_html_response()

@app.get("/summary", response_class=HTMLResponse)
@app.get("/devices", response_class=HTMLResponse)
@app.get("/destinations", response_class=HTMLResponse)
@app.get("/logs", response_class=HTMLResponse)
@app.get("/lte", response_class=HTMLResponse)
async def serve_admin_pages(request: Request):
    return get_no_cache_html_response()

# Static Files
app.mount("/", StaticFiles(directory=ADMIN_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
