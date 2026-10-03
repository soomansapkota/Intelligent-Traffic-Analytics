import unittest

from google.transit import gtfs_realtime_pb2

from src.processing.decode_feeds import decode_alerts, decode_trip_updates, decode_vehicle_positions


def _feed():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    return feed


def _alert_bytes(informed):
    feed = _feed()
    entity = feed.entity.add()
    entity.id = "alert1"
    entity.alert.cause = gtfs_realtime_pb2.Alert.MAINTENANCE
    entity.alert.effect = gtfs_realtime_pb2.Alert.MODIFIED_SERVICE
    entity.alert.header_text.translation.add(text="Trackwork", language="en")
    entity.alert.description_text.translation.add(text="Buses replace trains", language="en")
    for route_id, stop_id in informed:
        selector = entity.alert.informed_entity.add()
        selector.route_id = route_id
        if stop_id:
            selector.stop_id = stop_id
    return feed.SerializeToString()


class DecodeAlertsTest(unittest.TestCase):
    def test_repeated_route_collapses_to_one_row(self):
        # TfNSW lists an informed entity per affected stop, all naming the same route.
        raw = _alert_bytes([("SMNW_M1", "S1"), ("SMNW_M1", "S2"), ("SMNW_M1", "S3")])
        df = decode_alerts(raw)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.loc[0, "route_id"], "SMNW_M1")
        self.assertEqual(df.loc[0, "cause"], "MAINTENANCE")
        self.assertEqual(df.loc[0, "effect"], "MODIFIED_SERVICE")
        self.assertEqual(df.loc[0, "header_text"], "Trackwork")

    def test_distinct_routes_are_kept_in_order(self):
        raw = _alert_bytes([("R2", "S1"), ("R1", "S2"), ("R2", "S3")])
        df = decode_alerts(raw)
        self.assertListEqual(df["route_id"].tolist(), ["R2", "R1"])

    def test_alert_with_no_route_still_yields_a_row(self):
        df = decode_alerts(_alert_bytes([]))
        self.assertEqual(len(df), 1)
        self.assertIsNone(df.loc[0, "route_id"])


class DecodeTripUpdatesTest(unittest.TestCase):
    def test_one_row_per_stop_time_update(self):
        feed = _feed()
        entity = feed.entity.add()
        entity.id = "tu1"
        entity.trip_update.trip.trip_id = "T"
        entity.trip_update.trip.route_id = "SMNW_M1"
        entity.trip_update.trip.start_date = "20260911"
        for sequence, delay in [(1, 0), (2, 30)]:
            stu = entity.trip_update.stop_time_update.add()
            stu.stop_sequence = sequence
            stu.stop_id = f"S{sequence}"
            stu.arrival.time = 1786786200 + sequence
            stu.arrival.delay = delay

        df = decode_trip_updates(feed.SerializeToString())
        self.assertEqual(len(df), 2)
        self.assertListEqual(df["arrival_delay"].tolist(), [0, 30])
        self.assertEqual(df.loc[0, "schedule_relationship"], "SCHEDULED")


class DecodeVehiclePositionsTest(unittest.TestCase):
    def test_enums_decode_to_names(self):
        feed = _feed()
        entity = feed.entity.add()
        entity.id = "vp1"
        entity.vehicle.trip.trip_id = "T"
        entity.vehicle.vehicle.id = "V1"
        entity.vehicle.position.latitude = -33.7
        entity.vehicle.position.longitude = 150.9
        entity.vehicle.current_status = gtfs_realtime_pb2.VehiclePosition.STOPPED_AT
        entity.vehicle.occupancy_status = gtfs_realtime_pb2.VehiclePosition.FEW_SEATS_AVAILABLE

        df = decode_vehicle_positions(feed.SerializeToString())
        self.assertEqual(df.loc[0, "current_status"], "STOPPED_AT")
        self.assertEqual(df.loc[0, "occupancy_status"], "FEW_SEATS_AVAILABLE")
        self.assertEqual(df.loc[0, "vehicle_id"], "V1")

    def test_absent_occupancy_is_null(self):
        feed = _feed()
        entity = feed.entity.add()
        entity.id = "vp2"
        entity.vehicle.vehicle.id = "V2"
        df = decode_vehicle_positions(feed.SerializeToString())
        self.assertIsNone(df.loc[0, "occupancy_status"])


if __name__ == "__main__":
    unittest.main()
