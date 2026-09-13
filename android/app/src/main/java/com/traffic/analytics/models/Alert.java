package com.traffic.analytics.models;

import com.google.gson.annotations.SerializedName;

/**
 * Alert model - Service disruptions and announcements.
 */
public class Alert {
    @SerializedName("entity_id")
    public String entityId;
    public String cause;
    public String effect;
    public String header;
    public String description;
    @SerializedName("route_id")
    public String routeId;
    @SerializedName("fetched_at")
    public String fetchedAt;

    public Alert() {}

    public Alert(String entityId, String cause, String effect, String header, String description, String routeId) {
        this.entityId = entityId;
        this.cause = cause;
        this.effect = effect;
        this.header = header;
        this.description = description;
        this.routeId = routeId;
    }

    @Override
    public String toString() {
        return header != null ? header : "Alert: " + effect;
    }
}
