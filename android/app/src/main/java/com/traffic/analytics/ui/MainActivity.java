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
import com.traffic.analytics.adapters.AlertAdapter;
import com.traffic.analytics.api.ApiClient;
import com.traffic.analytics.api.TrafficApiService;
import com.traffic.analytics.models.ApiResponse;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

/**
 * MainActivity - Displays alerts and allows navigation to other screens.
 */
public class MainActivity extends AppCompatActivity {
    private RecyclerView alertsRecyclerView;
    private AlertAdapter alertAdapter;
    private SwipeRefreshLayout swipeRefresh;
    private Handler autoRefreshHandler;
    private Runnable autoRefreshRunnable;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        alertsRecyclerView = findViewById(R.id.recyclerViewAlerts);
        swipeRefresh = findViewById(R.id.swipeRefresh);

        alertsRecyclerView.setLayoutManager(new LinearLayoutManager(this));
        alertAdapter = new AlertAdapter();
        alertsRecyclerView.setAdapter(alertAdapter);

        // Swipe to refresh
        swipeRefresh.setOnRefreshListener(() -> {
            loadAlerts();
        });

        // Auto-refresh every 20 seconds
        autoRefreshHandler = new Handler(Looper.getMainLooper());
        setupAutoRefresh();

        loadAlerts();
    }

    private void setupAutoRefresh() {
        autoRefreshRunnable = () -> {
            if (!swipeRefresh.isRefreshing()) {
                loadAlerts();
            }
            autoRefreshHandler.postDelayed(autoRefreshRunnable, 20000); // 20 seconds
        };
        autoRefreshHandler.postDelayed(autoRefreshRunnable, 20000);
    }

    private void loadAlerts() {
        swipeRefresh.setRefreshing(true);
        TrafficApiService apiService = ApiClient.getInstance();

        apiService.getAlerts().enqueue(new Callback<ApiResponse.AlertsResponse>() {
            @Override
            public void onResponse(Call<ApiResponse.AlertsResponse> call, Response<ApiResponse.AlertsResponse> response) {
                swipeRefresh.setRefreshing(false);
                if (response.isSuccessful() && response.body() != null) {
                    alertAdapter.setAlerts(response.body().alerts);
                    int count = response.body().count;
                    Toast.makeText(MainActivity.this, "Loaded " + count + " alerts", Toast.LENGTH_SHORT).show();
                } else {
                    Toast.makeText(MainActivity.this, "Error: " + response.code(), Toast.LENGTH_SHORT).show();
                }
            }

            @Override
            public void onFailure(Call<ApiResponse.AlertsResponse> call, Throwable t) {
                swipeRefresh.setRefreshing(false);
                Toast.makeText(MainActivity.this, "Network error: " + t.getMessage(), Toast.LENGTH_SHORT).show();
            }
        });
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        autoRefreshHandler.removeCallbacks(autoRefreshRunnable);
    }
}
