import unittest

import pandas as pd

from src.processing.quality import column_summary, observation_share, poll_cadence, realtime_quality_report

NOW = int(pd.Timestamp("2026-08-15T09:31:00Z").timestamp())


def _rows():
    return pd.DataFrame([
        {"fetched_at": "2026-08-15T09:31:00+00:00", "trip_id": "A", "arrival_time": NOW - 60, "arrival_delay": 10, "note": "x"},
        {"fetched_at": "2026-08-15T09:31:00+00:00", "trip_id": "B", "arrival_time": NOW + 60, "arrival_delay": 0, "note": None},
        {"fetched_at": "2026-08-15T09:31:30+00:00", "trip_id": "A", "arrival_time": 0, "arrival_delay": 0, "note": "x"},
        {"fetched_at": "2026-08-15T09:33:00+00:00", "trip_id": "A", "arrival_time": NOW + 100, "arrival_delay": 5, "note": "y"},
    ])


class PollCadenceTest(unittest.TestCase):
    def test_counts_span_and_gaps(self):
        row = poll_cadence(_rows()).iloc[0]
        self.assertEqual(row["n_polls"], 3)
        self.assertEqual(row["span_minutes"], 2.0)
        self.assertEqual(row["median_gap_seconds"], 60)
        self.assertEqual(row["max_gap_seconds"], 90)


class ColumnSummaryTest(unittest.TestCase):
    def test_null_rate_and_cardinality(self):
        summary = column_summary(_rows())
        self.assertEqual(summary.loc["note", "null_frac"], 0.25)
        self.assertEqual(summary.loc["note", "n_unique"], 2)
        self.assertEqual(summary.loc["trip_id", "null_frac"], 0)


class ObservationShareTest(unittest.TestCase):
    def test_splits_passed_from_upcoming_and_ignores_missing_arrivals(self):
        share = observation_share(_rows()).set_index("stop_state")
        self.assertEqual(share.loc["passed", "n_rows"], 2)
        self.assertEqual(share.loc["upcoming", "n_rows"], 1)
        self.assertAlmostEqual(share.loc["passed", "row_share"], 2 / 3)
        self.assertEqual(share.loc["passed", "mean_delay"], 7.5)


class RealtimeQualityReportTest(unittest.TestCase):
    def test_one_row_per_feed(self):
        report = realtime_quality_report(_rows(), _rows(), _rows()).set_index("feed")
        self.assertListEqual(report.index.tolist(), ["trip_updates", "vehicle_positions", "alerts"])
        self.assertEqual(report.loc["alerts", "n_rows"], 4)
        self.assertEqual(report.loc["alerts", "n_polls"], 3)
        self.assertAlmostEqual(report.loc["alerts", "rows_per_poll"], 1.3)


if __name__ == "__main__":
    unittest.main()
