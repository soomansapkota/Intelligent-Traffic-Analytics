package com.traffic.analytics.models;

import com.google.gson.annotations.SerializedName;

/**
 * Route model - Sydney Metro route information.
 */
public class Route {
    @SerializedName("route_id")
    public String routeId;
    @SerializedName("route_name")
    public String routeName;

    public Route() {}

    public Route(String routeId, String routeName) {
        this.routeId = routeId;
        this.routeName = routeName;
    }

    @Override
    public String toString() {
        return routeName != null ? routeName : routeId;
    }
}
