package com.traffic.analytics.adapters;

import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.recyclerview.widget.RecyclerView;

import com.traffic.analytics.R;
import com.traffic.analytics.models.Delay;
import com.traffic.analytics.models.Departure;

import java.util.ArrayList;
import java.util.List;

/**
 * RecyclerView adapter for journey planner departures.
 */
public class DepartureAdapter extends RecyclerView.Adapter<DepartureAdapter.DepartureViewHolder> {
    private static final int COLOR_ON_TIME = Color.parseColor("#176B5B");
    private static final int COLOR_LATE = Color.parseColor("#B3541E");
    private static final int COLOR_EARLY = Color.parseColor("#0072CE");
    private static final int COLOR_SCHEDULED = Color.parseColor("#697873");

    private List<Departure> departures = new ArrayList<>();

    public void setDepartures(List<Departure> departures) {
        this.departures = departures != null ? departures : new ArrayList<>();
        notifyDataSetChanged();
    }

    @Override
    public DepartureViewHolder onCreateViewHolder(ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_departure, parent, false);
        return new DepartureViewHolder(view);
    }

    @Override
    public void onBindViewHolder(DepartureViewHolder holder, int position) {
        holder.bind(departures.get(position));
    }

    @Override
    public int getItemCount() {
        return departures.size();
    }

    public static class DepartureViewHolder extends RecyclerView.ViewHolder {
        private final TextView timesTextView;
        private final TextView countdownTextView;
        private final TextView destinationTextView;
        private final TextView punctualityTextView;
        private final TextView scheduledTextView;
        private final TextView positionTextView;
        private final TextView statusTextView;

        public DepartureViewHolder(View itemView) {
            super(itemView);
            timesTextView = itemView.findViewById(R.id.textViewTimes);
            countdownTextView = itemView.findViewById(R.id.textViewCountdown);
            destinationTextView = itemView.findViewById(R.id.textViewDestination);
            punctualityTextView = itemView.findViewById(R.id.textViewPunctuality);
            scheduledTextView = itemView.findViewById(R.id.textViewScheduled);
            positionTextView = itemView.findViewById(R.id.textViewPosition);
            statusTextView = itemView.findViewById(R.id.textViewStatus);
        }

        public void bind(Departure departure) {
            timesTextView.setText(departure.expectedDeparture + " → " + departure.scheduledArrival);
            countdownTextView.setText(departure.getCountdownText());
            destinationTextView.setText("To " + departure.destination + " · " + departure.durationMinutes + " min trip");

            boolean shifted = departure.expectedDeparture != null
                    && !departure.expectedDeparture.equals(departure.scheduledDeparture);
            String note = null;
            if (!departure.inTimetable) {
                note = "Extra service · not in the timetable"
                        + (shifted ? " · due " + departure.scheduledDeparture : "");
            } else if (shifted) {
                note = "Timetabled " + departure.scheduledDeparture;
            }
            scheduledTextView.setVisibility(note != null ? View.VISIBLE : View.GONE);
            scheduledTextView.setText(note);

            String position = departure.getPositionText();
            positionTextView.setVisibility(position != null ? View.VISIBLE : View.GONE);
            positionTextView.setText(position);

            int color = colorFor(departure.getPunctuality());
            GradientDrawable badge = new GradientDrawable();
            badge.setColor(color);
            badge.setCornerRadius(12 * itemView.getResources().getDisplayMetrics().density);
            punctualityTextView.setBackground(badge);
            punctualityTextView.setText(departure.getPunctualityText());

            if (departure.isModelPrediction()) {
                String status = "Now: " + Delay.formatDelay(departure.currentDelayMinutes);
                if (departure.predictedDelayMinutes != null) {
                    status += " · At your station: " + Delay.formatDelay(departure.predictedDelayMinutes) + " (our prediction)";
                }
                statusTextView.setText(status);
                statusTextView.setTextColor(color);
            } else if (departure.isTfnswForecast()) {
                statusTextView.setText("Not started yet · At your station: "
                        + Delay.formatDelay(departure.forecastDelayMinutes) + " (TfNSW forecast)");
                statusTextView.setTextColor(color);
            } else {
                statusTextView.setText("Timetable only · not in the live feed yet");
                statusTextView.setTextColor(COLOR_SCHEDULED);
            }
        }

        private static int colorFor(Departure.Punctuality punctuality) {
            switch (punctuality) {
                case LATE:
                    return COLOR_LATE;
                case EARLY:
                    return COLOR_EARLY;
                case ON_TIME:
                    return COLOR_ON_TIME;
                default:
                    return COLOR_SCHEDULED;
            }
        }
    }
}
