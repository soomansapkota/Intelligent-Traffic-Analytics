package com.traffic.analytics.adapters;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.recyclerview.widget.RecyclerView;

import com.traffic.analytics.R;
import com.traffic.analytics.models.Alert;

import java.util.ArrayList;
import java.util.List;

/**
 * RecyclerView adapter for displaying service alerts.
 */
public class AlertAdapter extends RecyclerView.Adapter<AlertAdapter.AlertViewHolder> {
    private List<Alert> alerts = new ArrayList<>();

    public void setAlerts(List<Alert> alerts) {
        this.alerts = alerts != null ? alerts : new ArrayList<>();
        notifyDataSetChanged();
    }

    @Override
    public AlertViewHolder onCreateViewHolder(ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_alert, parent, false);
        return new AlertViewHolder(view);
    }

    @Override
    public void onBindViewHolder(AlertViewHolder holder, int position) {
        Alert alert = alerts.get(position);
        holder.bind(alert);
    }

    @Override
    public int getItemCount() {
        return alerts.size();
    }

    public static class AlertViewHolder extends RecyclerView.ViewHolder {
        private TextView headerTextView;
        private TextView descriptionTextView;
        private TextView causeEffectTextView;

        public AlertViewHolder(View itemView) {
            super(itemView);
            headerTextView = itemView.findViewById(R.id.textViewHeader);
            descriptionTextView = itemView.findViewById(R.id.textViewDescription);
            causeEffectTextView = itemView.findViewById(R.id.textViewCauseEffect);
        }

        public void bind(Alert alert) {
            headerTextView.setText(alert.header != null ? alert.header : "Alert");
            descriptionTextView.setText(alert.description);
            causeEffectTextView.setText(String.format("Cause: %s | Effect: %s | Route: %s", 
                    alert.cause, alert.effect, alert.routeId));
        }
    }
}
