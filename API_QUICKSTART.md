# Quick Start: Run API Server for Mobile App

## Prerequisites

✓ PostgreSQL and Kafka running (docker containers)
✓ Python virtual environment activated
✓ Requirements installed (including fastapi/uvicorn)

## Step 1: Install FastAPI

```powershell
.venv\Scripts\activate
pip install fastapi uvicorn
```

## Step 2: Start the API Server

```powershell
cd c:\Users\acer\Downloads\ITA-Submission\Intelligent-Traffic-Analytics
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

**Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

## Step 3: Test the API

Open your browser and visit:

- **Swagger UI (Interactive Docs):** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/api/health
- **Service Alerts:** http://localhost:8000/api/alerts
- **Live Vehicles:** http://localhost:8000/api/vehicles
- **Predicted Delays:** http://localhost:8000/api/delays

## Step 4: Keep Pipeline Running (Optional)

In a separate terminal, keep collecting data:

```powershell
.venv\Scripts\activate
python -m src.orchestration.scheduler
```

This continuously fetches data every 30 seconds and populates the API endpoints.

## Step 5: Configure Android App

In [ApiClient.java](android/app/src/main/java/com/traffic/analytics/api/ApiClient.java), change:

```java
private static String BASE_URL = "http://10.0.2.2:8000"; // For emulator
// OR
private static String BASE_URL = "http://<YOUR_PC_IP>:8000"; // For physical device
```

Find your PC's IP:
```powershell
ipconfig
# Look for "IPv4 Address" (e.g., 192.168.1.100)
```

## Step 6: Run Android App

In Android Studio:
- Click `▶️ Run` (Shift+F10)
- Select emulator or physical device
- Wait for app to install and start

---

## Workflow

```
Terminal 1: Start PostgreSQL & Kafka
  docker compose up -d

Terminal 2: Run API Server
  python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000

Terminal 3: Collect Data (Optional)
  python -m src.orchestration.scheduler

Terminal 4: Android Studio
  ▶️ Run app on emulator/device
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Port 8000 already in use | `netstat -ano \| findstr 8000` then `taskkill /PID <PID>` |
| API returns no data | Run pipeline first: `python -m src.orchestration.pipeline` |
| App can't connect | Check firewall, update BASE_URL in ApiClient.java |
| Emulator network error | Use `10.0.2.2` instead of `localhost` |

---

## Next Steps

1. Keep API server running while testing app
2. Once working, see [MOBILE_APP_SETUP.md](MOBILE_APP_SETUP.md) for full guide
