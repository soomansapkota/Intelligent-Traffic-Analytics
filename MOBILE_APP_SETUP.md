# Mobile App Setup Guide

Complete setup for real-time traffic data display on Android.

## Architecture Overview

```
PostgreSQL Database
        ↓
   FastAPI Backend Server (http://server:8000)
        ↓
   Android App (Java) - Real-time Updates
```

---

## Part 1: Start the Backend API Server

### Step 1: Install FastAPI dependencies

```powershell
pip install fastapi uvicorn
# Or install all updated requirements:
pip install -r requirements.txt
```

### Step 2: Run the API Server

```powershell
# Navigate to project directory
cd c:\Users\acer\Downloads\ITA-Submission\Intelligent-Traffic-Analytics

# Activate virtual environment
.venv\Scripts\activate

# Start the FastAPI server
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

**Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 3: Verify API is running

Open browser and visit:
- **Health check:** http://localhost:8000/api/health
- **API Docs:** http://localhost:8000/docs (Interactive Swagger UI)
- **Alerts:** http://localhost:8000/api/alerts
- **Vehicles:** http://localhost:8000/api/vehicles
- **Delays:** http://localhost:8000/api/delays

---

## Part 2: Android App Setup

### Prerequisites

1. **Android Studio** (latest version)
   - Download: https://developer.android.com/studio
   
2. **Java Development Kit (JDK 11+)**
   - Installed with Android Studio or standalone

3. **Android SDK**
   - Android 8.0+ (API 24+)
   - Set via Android Studio

### Step 1: Create Android Project Structure

The following files are already created:

```
android/
├── app/
│   ├── build.gradle                 # App dependencies & build config
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml  # App permissions & activities
│       │   ├── java/com/traffic/analytics/
│       │   │   ├── api/
│       │   │   │   ├── ApiClient.java      # Retrofit client (singleton)
│       │   │   │   └── TrafficApiService.java  # API endpoints
│       │   │   ├── models/
│       │   │   │   ├── Alert.java
│       │   │   │   ├── Delay.java
│       │   │   │   ├── Vehicle.java
│       │   │   │   ├── Route.java
│       │   │   │   └── ApiResponse.java    # Response DTOs
│       │   │   ├── ui/
│       │   │   │   ├── MainActivity.java   # Service Alerts screen
│       │   │   │   ├── DelayPredictionActivity.java  # Delay predictions
│       │   │   │   └── VehicleTrackingActivity.java  # Live vehicles
│       │   │   └── adapters/
│       │   │       ├── AlertAdapter.java   # RecyclerView adapter
│       │   │       ├── DelayAdapter.java
│       │   │       └── VehicleAdapter.java
│       │   └── res/layout/
│       │       ├── activity_main.xml
│       │       ├── activity_delay_prediction.xml
│       │       ├── activity_vehicle_tracking.xml
│       │       ├── item_alert.xml
│       │       ├── item_delay.xml
│       │       └── item_vehicle.xml
```

### Step 2: Open in Android Studio

1. Open Android Studio
2. Select "Open" → Navigate to `android/` folder
3. Wait for Gradle to sync (first build takes 2-3 minutes)

### Step 3: Configure Server IP Address

**Important:** Update the server address in `ApiClient.java`

Find this line in [src/api/ApiClient.java](android/app/src/main/java/com/traffic/analytics/api/ApiClient.java#L16):

```java
private static String BASE_URL = "http://192.168.1.100:8000"; // Change to your server IP
```

Change `192.168.1.100` to:
- **Local testing:** `10.0.2.2:8000` (Android emulator default for localhost)
- **Physical device:** Your PC's IP address (find via `ipconfig` in Windows)
- **Deployed server:** Your API server's public IP

### Step 4: Set Android App Permissions

Already configured in [AndroidManifest.xml](android/app/src/main/AndroidManifest.xml):

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
```

### Step 5: Build and Run

**Option A: Android Emulator**

1. Click "Device Manager" in Android Studio
2. Create/select an emulator (e.g., Pixel 4, API 30)
3. Click ▶️ to start emulator
4. In Android Studio: Click `▶️ Run` (Shift+F10)

**Option B: Physical Android Device**

1. Enable "Developer Mode" on your Android phone
   - Settings → About Phone → Tap "Build Number" 7 times
   - Developer Options → Enable "USB Debugging"
2. Connect phone via USB
3. Click `▶️ Run` in Android Studio
4. Select your device

**Wait for:**
```
✓ App is installed and running
✓ You see "Sydney Metro - Real-time Analytics" on screen
```

---

## Part 3: Using the Android App

### Main Screens

**1. Service Alerts** (Default screen)
- Lists current service disruptions
- Shows cause, effect, affected routes
- Auto-refreshes every 20 seconds
- Swipe down to manually refresh

**2. Delay Predictions**
- Real-time delay predictions (5/10/15 minute horizons)
- Shows current vs predicted delay for each trip
- Status indicator: On time / Slightly delayed / Heavily delayed
- Auto-refreshes every 30 seconds

**3. Live Vehicle Tracking**
- Current position and status of all vehicles
- GPS coordinates, speed, route
- Shows occupancy status
- Auto-refreshes every 20 seconds

### Navigation

- Tap buttons at top to switch between screens
- Swipe down to manually refresh data
- Data updates automatically in background

---

## API Endpoints Reference

### Health Check
```
GET /api/health
Response: { "status": "ok", "timestamp": "2026-09-13T..." }
```

### Service Alerts
```
GET /api/alerts
Response: {
  "alerts": [
    {
      "entity_id": "alert_1",
      "cause": "CONSTRUCTION",
      "effect": "REDUCED_SERVICE",
      "header": "T1 Line Maintenance",
      "description": "Delays expected...",
      "route_id": "T1",
      "fetched_at": "2026-09-13T..."
    }
  ],
  "count": 5,
  "timestamp": "2026-09-13T..."
}
```

### Live Vehicles
```
GET /api/vehicles?route_id=T1
Response: {
  "vehicles": [
    {
      "vehicle_id": "1001",
      "vehicle_label": "M01",
      "trip_id": "trip_123",
      "route_id": "T1",
      "latitude": -33.8688,
      "longitude": 151.2093,
      "bearing": 180,
      "speed": 45.5,
      "status": "IN_TRANSIT",
      "occupancy": "MANY_SEATS_AVAILABLE",
      "timestamp": 1694592000,
      "fetched_at": "2026-09-13T..."
    }
  ],
  "count": 12,
  "timestamp": "2026-09-13T..."
}
```

### Predicted Delays
```
GET /api/delays?horizon_minutes=5
Response: {
  "horizon_minutes": 5,
  "delays": [
    {
      "trip_id": "trip_123",
      "route_id": "T1",
      "window_start": "2026-09-13T10:00:00",
      "current_delay_minutes": 2.5,
      "predicted_delay_minutes": 3.2,
      "stop_id": "stop_456",
      "stop_sequence": 5
    }
  ],
  "count": 45,
  "timestamp": "2026-09-13T..."
}
```

### Trip Details
```
GET /api/trip/{trip_id}
Response: {
  "trip_id": "trip_123",
  "route_id": "T1",
  "destination": "Central Station",
  "current_delay_minutes": 2.5,
  "predicted_delays": {
    "5_minutes": 3.2,
    "10_minutes": 3.8,
    "15_minutes": 4.1
  },
  "current_stop_name": "Barangaroo",
  "timestamp": "2026-09-13T..."
}
```

---

## Troubleshooting

### App can't connect to API
- **Check:** API server is running (`python -m uvicorn src.api.server:app`)
- **Check:** Server IP in `ApiClient.java` is correct
- **Check:** Firewall allows port 8000
- **Test:** Visit http://[SERVER_IP]:8000/api/health in browser

### No data showing in app
- **Check:** PostgreSQL has data (run pipeline first)
- **Check:** API health endpoint returns `"status": "ok"`
- **Check:** Database connection in `.env` is correct

### Emulator can't reach localhost
- **Android emulator default:** Use `10.0.2.2` instead of `localhost`
- **Physical device:** Use your PC's IP address

### Gradle build fails
- Clean build: `Build → Clean Project` → `Run`
- Update Android Studio and SDK
- Check Java version: `java -version` (should be 11+)

---

## Development Tips

### Adding New Features

1. **New API endpoint?** 
   - Add method to [TrafficApiService.java](android/app/src/main/java/com/traffic/analytics/api/TrafficApiService.java)
   - Add response class to [ApiResponse.java](android/app/src/main/java/com/traffic/analytics/models/ApiResponse.java)

2. **New model class?**
   - Create in `models/` folder
   - Use `@SerializedName` annotations for JSON field mapping

3. **New screen?**
   - Create Activity extending `AppCompatActivity`
   - Create layout XML in `res/layout/`
   - Add to `AndroidManifest.xml`

### Testing API Locally

Use the interactive Swagger UI:
```
http://localhost:8000/docs
```

Click endpoints to test directly with different parameters.

---

## Production Deployment

### For Real Users

1. **Secure the API:**
   - Add authentication (API key, OAuth)
   - Use HTTPS instead of HTTP
   - Rate limiting

2. **Host the backend:**
   - Deploy to cloud (AWS, Azure, Heroku, etc.)
   - Use managed PostgreSQL (RDS, Supabase, etc.)

3. **Update Android app:**
   - Change `BASE_URL` to production server
   - Update package name if publishing to Play Store
   - Generate signed APK for distribution

4. **Monitor:**
   - Set up logging
   - Monitor database performance
   - Health check endpoints

---

## References

- [Android Docs](https://developer.android.com/docs)
- [Retrofit Documentation](https://square.github.io/retrofit/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [RecyclerView Guide](https://developer.android.com/guide/topics/ui/layout/recyclerview)
