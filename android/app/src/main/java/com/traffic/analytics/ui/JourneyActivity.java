package com.traffic.analytics.ui;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.traffic.analytics.R;
import com.traffic.analytics.adapters.DepartureAdapter;
import com.traffic.analytics.api.ApiClient;
import com.traffic.analytics.models.ApiResponse;
import com.traffic.analytics.models.Departure;

import java.util.ArrayList;
import java.util.List;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

/**
 * JourneyActivity - Pick a From and To station and see the next trains between them,
 * with each running train's current and predicted delay.
 */
public class JourneyActivity extends AppCompatActivity {
    private static final int DEPARTURE_LIMIT = 6;

    private Spinner fromSpinner;
    private Spinner toSpinner;
    private TextView emptyTextView;
    private TextView summaryTextView;
    private SwipeRefreshLayout swipeRefresh;
    private DepartureAdapter departureAdapter;
    private ArrayAdapter<String> stationAdapter;
    private final List<String> stations = new ArrayList<>();
    private Handler autoRefreshHandler;
    private Runnable autoRefreshRunnable;
    private boolean searched = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_journey);

        fromSpinner = findViewById(R.id.spinnerFrom);
        toSpinner = findViewById(R.id.spinnerTo);
        emptyTextView = findViewById(R.id.textViewEmpty);
        summaryTextView = findViewById(R.id.textViewSummary);
        swipeRefresh = findViewById(R.id.swipeRefresh);

        stationAdapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, stations);
        stationAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        fromSpinner.setAdapter(stationAdapter);
        toSpinner.setAdapter(stationAdapter);

        RecyclerView departuresRecyclerView = findViewById(R.id.recyclerViewDepartures);
        departuresRecyclerView.setLayoutManager(new LinearLayoutManager(this));
        departureAdapter = new DepartureAdapter();
        departuresRecyclerView.setAdapter(departureAdapter);

        Button swapButton = findViewById(R.id.buttonSwap);
        swapButton.setOnClickListener(v -> {
            int from = fromSpinner.getSelectedItemPosition();
            fromSpinner.setSelection(toSpinner.getSelectedItemPosition());
            toSpinner.setSelection(from);
            if (searched) loadJourney();
        });
        Button findButton = findViewById(R.id.buttonFind);
        findButton.setOnClickListener(v -> loadJourney());

        swipeRefresh.setOnRefreshListener(() -> {
            if (searched) {
                loadJourney();
            } else {
                swipeRefresh.setRefreshing(false);
            }
        });

        // Auto-refresh every 30 seconds once a journey has been searched,
        // matching the 30-second collection cycle.
        autoRefreshHandler = new Handler(Looper.getMainLooper());
        autoRefreshRunnable = () -> {
            if (searched && !swipeRefresh.isRefreshing()) {
                loadJourney();
            }
            autoRefreshHandler.postDelayed(autoRefreshRunnable, 30000);
        };
        autoRefreshHandler.postDelayed(autoRefreshRunnable, 30000);

        loadStations();
    }

    private void loadStations() {
        ApiClient.getInstance().getStations().enqueue(new Callback<ApiResponse.StationsResponse>() {
            @Override
            public void onResponse(Call<ApiResponse.StationsResponse> call, Response<ApiResponse.StationsResponse> response) {
                if (response.isSuccessful() && response.body() != null && response.body().stations != null) {
                    stations.clear();
                    stations.addAll(response.body().stations);
                    stationAdapter.notifyDataSetChanged();
                    // Start with the two ends of the line.
                    fromSpinner.setSelection(0);
                    toSpinner.setSelection(stations.size() - 1);
                } else {
                    Toast.makeText(JourneyActivity.this, "Error loading stations: " + response.code(), Toast.LENGTH_SHORT).show();
                }
            }

            @Override
            public void onFailure(Call<ApiResponse.StationsResponse> call, Throwable t) {
                Toast.makeText(JourneyActivity.this, "Network error: " + t.getMessage(), Toast.LENGTH_SHORT).show();
            }
        });
    }

    private void loadJourney() {
        if (stations.isEmpty()) {
            Toast.makeText(this, "Stations are still loading", Toast.LENGTH_SHORT).show();
            return;
        }
        String from = (String) fromSpinner.getSelectedItem();
        String to = (String) toSpinner.getSelectedItem();
        if (from.equals(to)) {
            Toast.makeText(this, "Pick two different stations", Toast.LENGTH_SHORT).show();
            return;
        }
        searched = true;
        swipeRefresh.setRefreshing(true);

        ApiClient.getInstance().getJourney(from, to, DEPARTURE_LIMIT).enqueue(new Callback<ApiResponse.JourneyResponse>() {
            @Override
            public void onResponse(Call<ApiResponse.JourneyResponse> call, Response<ApiResponse.JourneyResponse> response) {
                swipeRefresh.setRefreshing(false);
                if (response.isSuccessful() && response.body() != null) {
                    departureAdapter.setDepartures(response.body().departures);
                    boolean none = response.body().count == 0;
                    emptyTextView.setVisibility(none ? View.VISIBLE : View.GONE);
                    emptyTextView.setText("No more trains today");
                    summaryTextView.setVisibility(none ? View.GONE : View.VISIBLE);
                    summaryTextView.setText(summarise(response.body().departures));
                } else {
                    Toast.makeText(JourneyActivity.this, "Error: " + response.code(), Toast.LENGTH_SHORT).show();
                }
            }

            @Override
            public void onFailure(Call<ApiResponse.JourneyResponse> call, Throwable t) {
                swipeRefresh.setRefreshing(false);
                Toast.makeText(JourneyActivity.this, "Network error: " + t.getMessage(), Toast.LENGTH_SHORT).show();
            }
        });
    }

    /**
     * One line counting the trains by punctuality, e.g. "3 late · 1 on time · 2 early · 1 not running yet".
     * Uses the same judgement as each card's badge, so the two always agree.
     */
    private static String summarise(List<Departure> departures) {
        int late = 0, onTime = 0, early = 0, scheduled = 0;
        if (departures != null) {
            for (Departure departure : departures) {
                switch (departure.getPunctuality()) {
                    case LATE: late++; break;
                    case ON_TIME: onTime++; break;
                    case EARLY: early++; break;
                    default: scheduled++; break;
                }
            }
        }
        List<String> parts = new ArrayList<>();
        if (late > 0) parts.add(late + " late");
        if (onTime > 0) parts.add(onTime + " on time");
        if (early > 0) parts.add(early + " early");
        if (scheduled > 0) parts.add(scheduled + " timetable only");
        return String.join(" · ", parts);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        autoRefreshHandler.removeCallbacks(autoRefreshRunnable);
    }
}
