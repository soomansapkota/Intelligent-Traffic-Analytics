package com.traffic.analytics.ui;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.traffic.analytics.R;
import com.traffic.analytics.adapters.VehicleAdapter;
import com.traffic.analytics.api.ApiClient;
import com.traffic.analytics.api.TrafficApiService;
import com.traffic.analytics.models.ApiResponse;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

/**
 * VehicleTrackingActivity - Shows live vehicle positions and status.
 */
public class VehicleTrackingActivity extends AppCompatActivity {
    private RecyclerView vehiclesRecyclerView;
    private VehicleAdapter vehicleAdapter;
    private SwipeRefreshLayout swipeRefresh;
    private Handler autoRefreshHandler;
    private Runnable autoRefreshRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_vehicle_tracking);

        vehiclesRecyclerView = findViewById(R.id.recyclerViewVehicles);
        swipeRefresh = findViewById(R.id.swipeRefresh);

        vehiclesRecyclerView.setLayoutManager(new LinearLayoutManager(this));
        vehicleAdapter = new VehicleAdapter();
        vehiclesRecyclerView.setAdapter(vehicleAdapter);

        swipeRefresh.setOnRefreshListener(() -> loadVehicles());
        setupAutoRefresh();
        loadVehicles();
    }

    private void setupAutoRefresh() {
        autoRefreshHandler = new Handler(Looper.getMainLooper());
        autoRefreshRunnable = () -> {
            if (!swipeRefresh.isRefreshing()) {
                loadVehicles();
            }
            autoRefreshHandler.postDelayed(autoRefreshRunnable, 20000); // 20 seconds
        };
        autoRefreshHandler.postDelayed(autoRefreshRunnable, 20000);
    }

    private void loadVehicles() {
        swipeRefresh.setRefreshing(true);
        TrafficApiService apiService = ApiClient.getInstance();

        apiService.getVehicles(null).enqueue(new Callback<ApiResponse.VehiclesResponse>() {
            @Override
            public void onResponse(Call<ApiResponse.VehiclesResponse> call, Response<ApiResponse.VehiclesResponse> response) {
                swipeRefresh.setRefreshing(false);
                if (response.isSuccessful() && response.body() != null) {
                    vehicleAdapter.setVehicles(response.body().vehicles);
                    int count = response.body().count;
                    Toast.makeText(VehicleTrackingActivity.this, "Tracking " + count + " vehicles", Toast.LENGTH_SHORT).show();
                } else {
                    Toast.makeText(VehicleTrackingActivity.this, "Error: " + response.code(), Toast.LENGTH_SHORT).show();
                }
            }

            @Override
            public void onFailure(Call<ApiResponse.VehiclesResponse> call, Throwable t) {
                swipeRefresh.setRefreshing(false);
                Toast.makeText(VehicleTrackingActivity.this, "Network error: " + t.getMessage(), Toast.LENGTH_SHORT).show();
            }
        });
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        autoRefreshHandler.removeCallbacks(autoRefreshRunnable);
    }
}
