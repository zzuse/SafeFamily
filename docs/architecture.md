## Architecture Overview
```
Internet
    │
    ↓
[Port 443] HTTPS
    │
    ↓
┌─────────────────┐
│  Nginx          │  - SSL Termination
│  (Reverse Proxy)│  - Static Files
│                 │  - Load Balancing
└────────┬────────┘  - Rate Limiting
         │
         ↓
[127.0.0.1:8000] HTTP (Internal)
         │
         ↓
┌─────────────────┐
│  Gunicorn       │  - WSGI Server
│  (App Server)   │  - Worker Processes
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Flask/Django   │  - Application Logic
│  Application    │  - Business Rules
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  PostgreSQL     │  - Database
└─────────────────┘
```