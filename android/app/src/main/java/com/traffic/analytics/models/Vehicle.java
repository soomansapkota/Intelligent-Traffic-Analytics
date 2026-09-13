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
