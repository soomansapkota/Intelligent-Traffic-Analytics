package com.traffic.analytics.api;

import com.traffic.analytics.models.Alert;
import com.traffic.analytics.models.Delay;
import com.traffic.analytics.models.Route;
import com.traffic.analytics.models.Vehicle;
import com.traffic.analytics.models.ApiResponse;

import java.util.List;

import retrofit2.Call;
import retrofit2.http.GET;
import retrofit2.http.Path;
import retrofit2.http.Query;

/**
 * Retrofit API interface for Traffic Analytics backend.
 * Base URL: http://your-server:8000
 */
public interface TrafficApiService {

    @GET("/api/health")
    Call<ApiResponse.HealthResponse> checkHealth();

    @GET("/api/alerts")
    Call<ApiResponse.AlertsResponse> getAlerts();

    @GET("/api/vehicles")
    Call<ApiResponse.VehiclesResponse> getVehicles(
            @Query("route_id") String routeId
    );

    @GET("/api/delays")
    Call<ApiResponse.DelaysResponse> getPredictedDelays(
            @Query("route_id") String routeId,
            @Query("horizon_minutes") int horizonMinutes
    );

    @GET("/api/routes")
    Call<ApiResponse.RoutesResponse> getRoutes();

    @GET("/api/trip/{trip_id}")
    Call<ApiResponse.TripDetailResponse> getTripDetails(
            @Path("trip_id") String tripId
    );
}
