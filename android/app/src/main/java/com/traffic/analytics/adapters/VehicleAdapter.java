package com.traffic.analytics.adapters;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.recyclerview.widget.RecyclerView;

import com.traffic.analytics.R;
import com.traffic.analytics.models.Vehicle;

import java.util.ArrayList;
import java.util.List;

/**
 * RecyclerView adapter for displaying live vehicle positions.
 */
public class VehicleAdapter extends RecyclerView.Adapter<VehicleAdapter.VehicleViewHolder> {
    private List<Vehicle> vehicles = new ArrayList<>();

    public void setVehicles(List<Vehicle> vehicles) {
        this.vehicles = vehicles != null ? vehicles : new ArrayList<>();
        notifyDataSetChanged();
    }

    @Override
    public VehicleViewHolder onCreateViewHolder(ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_vehicle, parent, false);
        return new VehicleViewHolder(view);
    }

    @Override
    public void onBindViewHolder(VehicleViewHolder holder, int position) {
        Vehicle vehicle = vehicles.get(position);
        holder.bind(vehicle);
    }

    @Override
    public int getItemCount() {
        return vehicles.size();
    }

    public static class VehicleViewHolder extends RecyclerView.ViewHolder {
        private TextView vehicleLabelTextView;
        private TextView routeIdTextView;
        private TextView locationTextView;
        private TextView speedTextView;
        private TextView statusTextView;

        public VehicleViewHolder(View itemView) {
            super(itemView);
            vehicleLabelTextView = itemView.findViewById(R.id.textViewVehicleLabel);
            routeIdTextView = itemView.findViewById(R.id.textViewRouteId);
            locationTextView = itemView.findViewById(R.id.textViewLocation);
            speedTextView = itemView.findViewById(R.id.textViewSpeed);
            statusTextView = itemView.findViewById(R.id.textViewStatus);
        }

        public void bind(Vehicle vehicle) {
            vehicleLabelTextView.setText(vehicle.vehicleLabel != null ? vehicle.vehicleLabel : vehicle.vehicleId);
            routeIdTextView.setText("Route: " + vehicle.routeId);
            
            String location = vehicle.latitude != null && vehicle.longitude != null
                    ? String.format("GPS: %.4f, %.4f", vehicle.latitude, vehicle.longitude)
                    : "GPS: Unknown";
            locationTextView.setText(location);
            
            String speed = vehicle.speed != null
                    ? String.format("Speed: %.1f km/h", vehicle.speed)
                    : "Speed: N/A";
            speedTextView.setText(speed);
            
            statusTextView.setText("Status: " + (vehicle.status != null ? vehicle.status : "Unknown"));
        }
    }
}
