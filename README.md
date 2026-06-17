# Nmap API Production Server

A centralized API hub for managed device tasks with intelligent GPS simulation and identity spoofing.

## Quick Start
1. **Sync Data**: `./cron.sh` (Runs sync, aggregation, and optimization)
2. **API Server**: Managed by PM2 as `nmap-api`. Access at `http://localhost:8000`.

## Architecture
- `core/`: Primary business logic (Sync, Aggregator, Optimizer, Scraper).
- `api_server.py`: FastAPI server for device communication.
- `logs/`: Execution logs for all automated tasks.
- `data/hashes/`: Sync state tracking.

## Operational Commands
- Check status: `pm2 status`
- Monitor logs: `pm2 logs nmap-api`
- Manual sync: `./cron.sh`
