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
import com.traffic.analytics.adapters.DelayAdapter;
import com.traffic.analytics.api.ApiClient;
import com.traffic.analytics.api.TrafficApiService;
import com.traffic.analytics.models.ApiResponse;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

/**
 * DelayPredictionActivity - Shows predicted delays for trips at different horizons.
 */
public class DelayPredictionActivity extends AppCompatActivity {
    private RecyclerView delaysRecyclerView;
    private DelayAdapter delayAdapter;
    private SwipeRefreshLayout swipeRefresh;
    private Handler autoRefreshHandler;
    private Runnable autoRefreshRunnable;
    private int horizonMinutes = 5; // Default: 5 minute horizon

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_delay_prediction);

        delaysRecyclerView = findViewById(R.id.recyclerViewDelays);
        swipeRefresh = findViewById(R.id.swipeRefresh);

        delaysRecyclerView.setLayoutManager(new LinearLayoutManager(this));
        delayAdapter = new DelayAdapter();
        delaysRecyclerView.setAdapter(delayAdapter);

        swipeRefresh.setOnRefreshListener(() -> loadDelays());
        setupAutoRefresh();
        loadDelays();
    }

    private void setupAutoRefresh() {
        autoRefreshHandler = new Handler(Looper.getMainLooper());
        autoRefreshRunnable = () -> {
            if (!swipeRefresh.isRefreshing()) {
                loadDelays();
            }
            autoRefreshHandler.postDelayed(autoRefreshRunnable, 30000); // 30 seconds
        };
        autoRefreshHandler.postDelayed(autoRefreshRunnable, 30000);
    }

    private void loadDelays() {
        swipeRefresh.setRefreshing(true);
        TrafficApiService apiService = ApiClient.getInstance();

        apiService.getPredictedDelays(null, horizonMinutes).enqueue(new Callback<ApiResponse.DelaysResponse>() {
            @Override
            public void onResponse(Call<ApiResponse.DelaysResponse> call, Response<ApiResponse.DelaysResponse> response) {
                swipeRefresh.setRefreshing(false);
                if (response.isSuccessful() && response.body() != null) {
                    delayAdapter.setDelays(response.body().delays);
                    int count = response.body().count;
                    Toast.makeText(DelayPredictionActivity.this, "Loaded " + count + " delays", Toast.LENGTH_SHORT).show();
                } else {
                    Toast.makeText(DelayPredictionActivity.this, "Error: " + response.code(), Toast.LENGTH_SHORT).show();
                }
            }

            @Override
            public void onFailure(Call<ApiResponse.DelaysResponse> call, Throwable t) {
                swipeRefresh.setRefreshing(false);
                Toast.makeText(DelayPredictionActivity.this, "Network error: " + t.getMessage(), Toast.LENGTH_SHORT).show();
            }
        });
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        autoRefreshHandler.removeCallbacks(autoRefreshRunnable);
    }
}
