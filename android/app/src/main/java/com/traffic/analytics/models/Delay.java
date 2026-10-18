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
    @SerializedName("stop_name")
    public String stopName;
    @SerializedName("destination")
    public String destination;
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
        long minutes = Math.round(currentDelayMinutes);
        if (minutes < 0) return "Running early";
        if (minutes == 0) return "On time";
        if (minutes <= 5) return "Slightly delayed";
        return "Heavily delayed";
    }

    /**
     * Where the train is, e.g. "At Chatswood Station, Platform 2 · to Tallawong".
     * Null when the API sent no station name (trips not matched to the timetable).
     */
    public String getLocationText() {
        if (stopName == null || stopName.isEmpty()) return null;
        String text = "At " + stopName;
        if (destination != null && !destination.isEmpty()) text += " · to " + destination;
        return text;
    }

    /**
     * Format a delay the way TripView does, rounded to whole minutes:
     * "On time", "1 min late", "2 mins early". Null gives "N/A".
     */
    public static String formatDelay(Double delayMinutes) {
        if (delayMinutes == null) return "N/A";
        long minutes = Math.round(delayMinutes);
        if (minutes == 0) return "On time";
        long abs = Math.abs(minutes);
        return abs + (abs == 1 ? " min " : " mins ") + (minutes > 0 ? "late" : "early");
    }

    @Override
    public String toString() {
        return String.format("Trip %s: %s (current) → %s (predicted)",
                tripId, formatDelay(currentDelayMinutes), formatDelay(predictedDelayMinutes));
    }
}
