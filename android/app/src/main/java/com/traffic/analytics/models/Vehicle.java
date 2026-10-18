package com.traffic.analytics.models;

import com.google.gson.annotations.SerializedName;

/**
 * Vehicle model - Real-time vehicle positions and status.
 */
public class Vehicle {
    @SerializedName("vehicle_id")
    public String vehicleId;
    @SerializedName("vehicle_label")
    public String vehicleLabel;
    @SerializedName("trip_id")
    public String tripId;
    @SerializedName("route_id")
    public String routeId;
    public Double latitude;
    public Double longitude;
    @SerializedName("nearest_station")
    public String nearestStation;
    @SerializedName("station_distance_m")
    public Integer stationDistanceM;
    public Double bearing;
    public Double speed;
    @SerializedName("stop_sequence")
    public int stopSequence;
    public String status; // IN_TRANSIT, STOPPED_AT, INCOMING_AT
    public String occupancy;
    public Long timestamp;
    @SerializedName("fetched_at")
    public String fetchedAt;

    public Vehicle() {}

    /**
     * Where the train is by name: "At Chatswood Station" within 300 m of a
     * station, otherwise "Near Chatswood Station (1.2 km)". Null when the
     * API found no station (no GPS, or static stops not loaded).
     */
    public String getPlaceText() {
        if (nearestStation == null || stationDistanceM == null) return null;
        if (stationDistanceM <= 300) return "At " + nearestStation;
        String distance = stationDistanceM < 1000
                ? stationDistanceM + " m"
                : String.format("%.1f km", stationDistanceM / 1000.0);
        return "Near " + nearestStation + " (" + distance + ")";
    }

    /** Speed in km/h; the GTFS-Realtime feed reports metres per second. */
    public Double getSpeedKmh() {
        return speed != null ? speed * 3.6 : null;
    }

    public Vehicle(String vehicleId, String vehicleLabel, String tripId, String routeId,
                   Double latitude, Double longitude) {
        this.vehicleId = vehicleId;
        this.vehicleLabel = vehicleLabel;
        this.tripId = tripId;
        this.routeId = routeId;
        this.latitude = latitude;
        this.longitude = longitude;
    }

    @Override
    public String toString() {
        return vehicleLabel != null ? vehicleLabel : vehicleId;
    }
}
