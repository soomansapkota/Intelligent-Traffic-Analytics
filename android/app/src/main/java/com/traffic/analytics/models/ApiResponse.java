package com.traffic.analytics.models;

import com.google.gson.annotations.SerializedName;
import java.util.List;

/**
 * Model classes for API responses.
 */
public class ApiResponse {

    public static class HealthResponse {
        public String status;
        public String timestamp;
    }

    public static class AlertsResponse {
        public List<Alert> alerts;
        public int count;
        public String timestamp;
    }

    public static class VehiclesResponse {
        public List<Vehicle> vehicles;
        public int count;
        public String timestamp;
    }

    public static class DelaysResponse {
        @SerializedName("horizon_minutes")
        public int horizonMinutes;
        public List<Delay> delays;
        public int count;
        public String timestamp;
    }

    public static class RoutesResponse {
        public List<Route> routes;
        public int count;
        public String timestamp;
    }

    public static class TripDetailResponse {
        @SerializedName("trip_id")
        public String tripId;
        @SerializedName("route_id")
        public String routeId;
        public String destination;
        @SerializedName("service_date")
        public String serviceDate;
        @SerializedName("observed_time")
        public String observedTime;
        @SerializedName("current_delay_minutes")
        public Double currentDelayMinutes;
        @SerializedName("current_stop_id")
        public String currentStopId;
        @SerializedName("current_stop_name")
        public String currentStopName;
        @SerializedName("stop_sequence")
        public int stopSequence;
        @SerializedName("predicted_delays")
        public PredictedDelays predictedDelays;
        public String timestamp;

        public static class PredictedDelays {
            @SerializedName("5_minutes")
            public Double fiveMinutes;
            @SerializedName("10_minutes")
            public Double tenMinutes;
            @SerializedName("15_minutes")
            public Double fifteenMinutes;
        }
    }
}
