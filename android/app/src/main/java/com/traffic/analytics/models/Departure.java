package com.traffic.analytics.models;

import com.google.gson.annotations.SerializedName;

/**
 * Departure model - One train from the journey planner (/api/journey).
 * Times are 24-hour "HH:mm" strings; delays are in minutes.
 */
public class Departure {
    @SerializedName("trip_id")
    public String tripId;
    @SerializedName("destination")
    public String destination;
    @SerializedName("scheduled_departure")
    public String scheduledDeparture;
    @SerializedName("scheduled_arrival")
    public String scheduledArrival;
    @SerializedName("expected_departure")
    public String expectedDeparture;
    @SerializedName("duration_minutes")
    public int durationMinutes;
    @SerializedName("minutes_until_departure")
    public int minutesUntilDeparture;
    @SerializedName("live")
    public boolean live;
    /** False for extra trains TfNSW runs outside the published timetable. */
    @SerializedName("in_timetable")
    public boolean inTimetable = true;
    @SerializedName("current_stop_name")
    public String currentStopName;
    @SerializedName("current_delay_minutes")
    public Double currentDelayMinutes;
    @SerializedName("predicted_delay_minutes")
    public Double predictedDelayMinutes;
    @SerializedName("horizon_minutes")
    public Integer horizonMinutes;
    /** TfNSW's own forecast delay at the boarding station, for trains in the live feed. */
    @SerializedName("forecast_delay_minutes")
    public Double forecastDelayMinutes;
    /** What the expected time is based on: "model", "tfnsw", or null for the timetable alone. */
    @SerializedName("delay_source")
    public String delaySource;

    public boolean isModelPrediction() {
        return "model".equals(delaySource);
    }

    public boolean isTfnswForecast() {
        return "tfnsw".equals(delaySource);
    }

    /** "Now", "1 min" or "12 mins" until the train leaves. */
    public String getCountdownText() {
        if (minutesUntilDeparture <= 0) return "Now";
        return minutesUntilDeparture + (minutesUntilDeparture == 1 ? " min" : " mins");
    }

    /**
     * The delay expected at the boarding station: the model's prediction (or the
     * current delay) for running trains, TfNSW's forecast for trains not started
     * yet, and null when only the timetable is known.
     */
    public Double getHeadlineDelayMinutes() {
        if (isModelPrediction()) {
            return predictedDelayMinutes != null ? predictedDelayMinutes : currentDelayMinutes;
        }
        if (isTfnswForecast()) return forecastDelayMinutes;
        return null;
    }

    /** Whether the train is expected late, early or on time at the boarding station. */
    public enum Punctuality { ON_TIME, LATE, EARLY, SCHEDULED }

    /**
     * Judged on the headline delay rounded to whole minutes, the same rounding
     * Delay.formatDelay uses, so the badge and the delay text always agree.
     * SCHEDULED only when neither the model nor TfNSW has a delay to judge.
     */
    public Punctuality getPunctuality() {
        Double delay = getHeadlineDelayMinutes();
        if (delay == null) return Punctuality.SCHEDULED;
        long minutes = Math.round(delay);
        if (minutes > 0) return Punctuality.LATE;
        if (minutes < 0) return Punctuality.EARLY;
        return Punctuality.ON_TIME;
    }

    /** Badge text, e.g. "Late · 3 mins", "Early · 1 min", "On time", "Scheduled". */
    public String getPunctualityText() {
        Punctuality punctuality = getPunctuality();
        if (punctuality == Punctuality.ON_TIME) return "On time";
        if (punctuality == Punctuality.SCHEDULED) return "Scheduled";
        long abs = Math.abs(Math.round(getHeadlineDelayMinutes()));
        String amount = abs + (abs == 1 ? " min" : " mins");
        return (punctuality == Punctuality.LATE ? "Late · " : "Early · ") + amount;
    }

    /** Where the train is now, e.g. "Now at Victoria Cross Station". Null if not running yet. */
    public String getPositionText() {
        if (!live || currentStopName == null || currentStopName.isEmpty()) return null;
        return "Now at " + currentStopName.split(",")[0].trim();
    }
}
