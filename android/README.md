# Android Project Initialization

This folder contains the complete Android app source code in Java.

## Folder Structure

```
android/
├── app/
│   ├── build.gradle                         # App configuration
│   ├── proguard-rules.pro                   # Proguard rules
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml          # App manifest
│       │   ├── java/com/traffic/analytics/
│       │   │   ├── api/
│       │   │   │   ├── ApiClient.java       # Retrofit singleton
│       │   │   │   └── TrafficApiService.java  # API interface
│       │   │   ├── models/
│       │   │   │   ├── Alert.java
│       │   │   │   ├── Delay.java
│       │   │   │   ├── Vehicle.java
│       │   │   │   ├── Route.java
│       │   │   │   └── ApiResponse.java
│       │   │   ├── ui/
│       │   │   │   ├── MainActivity.java
│       │   │   │   ├── DelayPredictionActivity.java
│       │   │   │   └── VehicleTrackingActivity.java
│       │   │   └── adapters/
│       │   │       ├── AlertAdapter.java
│       │   │       ├── DelayAdapter.java
│       │   │       └── VehicleAdapter.java
│       │   └── res/
│       │       ├── layout/
│       │       │   ├── activity_main.xml
│       │       │   ├── activity_delay_prediction.xml
│       │       │   ├── activity_vehicle_tracking.xml
│       │       │   ├── item_alert.xml
│       │       │   ├── item_delay.xml
│       │       │   └── item_vehicle.xml
│       │       ├── values/
│       │       │   └── strings.xml          # App strings (create manually)
│       │       └── mipmap/
│       │           └── ic_launcher.xml      # App icon (generated)
│       └── test/
│           └── (unit tests)
├── gradle/
│   └── wrapper/                             # Gradle wrapper
├── settings.gradle                          # Project settings
├── gradle.properties                        # Gradle properties
└── build.gradle                             # Project build configuration
```

## Quick Setup

### Option 1: Use Android Studio (Recommended)

1. **Open Android Studio**
2. **Click "Open"** → Select `android/` folder
3. **Wait for Gradle sync** (2-3 minutes on first run)
4. **Update BASE_URL** in [ApiClient.java](app/src/main/java/com/traffic/analytics/api/ApiClient.java#L16)
5. **Click ▶️ Run** to build and deploy

### Option 2: Command Line Build

```bash
cd android

# Build APK
./gradlew assembleDebug

# Run on connected device
./gradlew installDebug

# Run tests
./gradlew test
```

## Key Files to Customize

### 1. Update Server Address

**File:** [app/src/main/java/com/traffic/analytics/api/ApiClient.java](app/src/main/java/com/traffic/analytics/api/ApiClient.java#L16)

```java
private static String BASE_URL = "http://192.168.1.100:8000";
// Change to your server:
// - Emulator: "http://10.0.2.2:8000"
// - Physical device: "http://<YOUR_PC_IP>:8000"
```

### 2. Customize App Strings

**File:** `app/src/main/res/values/strings.xml` (create if missing)

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Traffic Analytics</string>
    <string name="title_alerts">Service Alerts</string>
    <string name="title_delays">Delay Predictions</string>
    <string name="title_vehicles">Live Vehicles</string>
</resources>
```

### 3. Update App Icon

Replace `app/src/main/res/mipmap/ic_launcher.png` with your custom icon.

## Dependencies

**API Communication:**
- Retrofit 2.10.0 (HTTP client)
- OkHttp 4.11.0 (HTTP networking)
- Gson 2.10.1 (JSON parsing)

**UI Components:**
- AndroidX AppCompat 1.6.1
- Material Design 1.11.0
- RecyclerView 1.3.2
- SwipeRefreshLayout 1.1.0

**Async Operations:**
- Kotlin Coroutines 1.7.3
- AndroidX Lifecycle 2.7.0

## Architecture

```
MainActivity (Service Alerts)
    ↓
DelayPredictionActivity (Predicted Delays)
    ↓
VehicleTrackingActivity (Live Vehicles)

Each Activity:
  - Uses Retrofit to call API
  - Updates RecyclerView adapter with data
  - Auto-refreshes every 20-30 seconds
  - Supports manual swipe-to-refresh
```

## Testing

### Unit Tests

```bash
./gradlew test
```

### Integration Tests

```bash
./gradlew connectedAndroidTest
```

### Manual Testing

1. Make sure API server is running: `http://localhost:8000/docs`
2. Run app on emulator or device
3. Check each screen for data
4. Test pull-to-refresh
5. Monitor network calls in Logcat

## Build Variants

**Debug Build** (Development)
```bash
./gradlew assembleDebug
```

**Release Build** (Production)
```bash
./gradlew assembleRelease
```

To sign release build:
```bash
./gradlew bundleRelease  # For Play Store
./gradlew assembleRelease -P storeFile=keystore.jks  # With custom keystore
```

## Deployment

### Emulator
```bash
# Start emulator
emulator -avd Pixel_4_API_30

# Install APK
adb install app/build/outputs/apk/debug/app-debug.apk

# Launch app
adb shell am start -n com.traffic.analytics/.ui.MainActivity
```

### Physical Device
```bash
# Enable USB Debugging on phone
# Connect via USB
adb devices  # Should list your device

# Install
./gradlew installDebug

# View logs
adb logcat -s "*:V"
```

### Play Store
1. Sign APK with keystore
2. Create Play Store listing
3. Upload `app/build/outputs/bundle/release/app-release.aab`

## Troubleshooting

### Gradle Sync Fails
```bash
./gradlew clean
./gradlew build
```

### Java Version Mismatch
```bash
# Check current Java version
java -version

# Should be 11 or higher
# If not, update JAVA_HOME environment variable
```

### API Connection Fails
- Ensure BASE_URL is correct
- Check firewall allows port 8000
- Verify API server is running
- Use `adb logcat` to see network errors

## Development Workflow

```
1. Edit Java code
2. Click ▶️ Run
3. App recompiles and installs
4. Test on emulator/device
5. Logcat shows debug output
```

Real-time debugging:
```bash
adb logcat -s "TrafficAnalytics:*"
```

## Next Steps

1. [Start API Server](../API_QUICKSTART.md)
2. [Open project in Android Studio](#option-1-use-android-studio-recommended)
3. Update BASE_URL for your network
4. Run on emulator or physical device
5. See [Full Setup Guide](../MOBILE_APP_SETUP.md) for features and usage

---

**Questions?** Check [MOBILE_APP_SETUP.md](../MOBILE_APP_SETUP.md) for detailed documentation.
