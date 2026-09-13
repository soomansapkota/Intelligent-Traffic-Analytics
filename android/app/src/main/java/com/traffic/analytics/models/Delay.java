package com.traffic.analytics.models;

import com.google.gson.annotations.SerializedName;

/**
 * Delay model - Predicted and current delays per trip.
 */
public class Delay {
    @SerializedName("trip_id")
    public String tripId;
    @SerializedName("route_id")
    public String routeId;
    @SerializedName("window_start")
    public String windowStart;
    @SerializedName("current_delay_minutes")
    public Double currentDelayMinutes;
    @SerializedName("predicted_delay_minutes")
    public Double predictedDelayMinutes;
    @SerializedName("stop_id")
    public String stopId;
    @SerializedName("stop_sequence")
    public int stopSequence;

    public Delay() {}

    public Delay(String tripId, String routeId, Double currentDelay, Double predictedDelay) {
        this.tripId = tripId;
        this.routeId = routeId;
        this.currentDelayMinutes = currentDelay;
        this.predictedDelayMinutes = predictedDelay;
    }

    public String getDelayStatus() {
        if (currentDelayMinutes == null) return "No data";
        if (currentDelayMinutes <= 1) return "On time";
        if (currentDelayMinutes <= 5) return "Slightly delayed";
        return "Heavily delayed";
    }

    @Override
    public String toString() {
        return String.format("Trip %s: %+.1f min (current) → %+.1f min (predicted)",
                tripId, currentDelayMinutes != null ? currentDelayMinutes : 0,
                predictedDelayMinutes != null ? predictedDelayMinutes : 0);
    }
}
