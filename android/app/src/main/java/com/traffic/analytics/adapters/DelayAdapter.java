package com.traffic.analytics.adapters;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.recyclerview.widget.RecyclerView;

import com.traffic.analytics.R;
import com.traffic.analytics.models.Delay;

import java.util.ArrayList;
import java.util.List;

/**
 * RecyclerView adapter for displaying predicted delays.
 */
public class DelayAdapter extends RecyclerView.Adapter<DelayAdapter.DelayViewHolder> {
    private List<Delay> delays = new ArrayList<>();

    public void setDelays(List<Delay> delays) {
        this.delays = delays != null ? delays : new ArrayList<>();
        notifyDataSetChanged();
    }

    @Override
    public DelayViewHolder onCreateViewHolder(ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_delay, parent, false);
        return new DelayViewHolder(view);
    }

    @Override
    public void onBindViewHolder(DelayViewHolder holder, int position) {
        Delay delay = delays.get(position);
        holder.bind(delay);
    }

    @Override
    public int getItemCount() {
        return delays.size();
    }

    public static class DelayViewHolder extends RecyclerView.ViewHolder {
        private TextView tripIdTextView;
        private TextView routeIdTextView;
        private TextView locationTextView;
        private TextView currentDelayTextView;
        private TextView predictedDelayTextView;
        private TextView statusTextView;

        public DelayViewHolder(View itemView) {
            super(itemView);
            tripIdTextView = itemView.findViewById(R.id.textViewTripId);
            routeIdTextView = itemView.findViewById(R.id.textViewRouteId);
            locationTextView = itemView.findViewById(R.id.textViewLocation);
            currentDelayTextView = itemView.findViewById(R.id.textViewCurrentDelay);
            predictedDelayTextView = itemView.findViewById(R.id.textViewPredictedDelay);
            statusTextView = itemView.findViewById(R.id.textViewStatus);
        }

        public void bind(Delay delay) {
            tripIdTextView.setText("Trip: " + delay.tripId);
            routeIdTextView.setText("Route: " + delay.routeId);

            String location = delay.getLocationText();
            locationTextView.setVisibility(location != null ? View.VISIBLE : View.GONE);
            locationTextView.setText(location);
            
            currentDelayTextView.setText("Current: " + Delay.formatDelay(delay.currentDelayMinutes));
            predictedDelayTextView.setText("Predicted: " + Delay.formatDelay(delay.predictedDelayMinutes));
            
            statusTextView.setText(delay.getDelayStatus());
        }
    }
}
