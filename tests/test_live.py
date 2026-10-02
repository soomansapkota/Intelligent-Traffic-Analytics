import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pandas as pd

from src.orchestration.pipeline import predict_live, run_once
from src.storage.db import get_engine, init_db, read_recent


class ReadRecentTest(unittest.TestCase):
    def test_returns_only_rows_fetched_since_the_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = get_engine(f"sqlite:///{Path(tmp) / 'test.db'}")
            init_db(engine)
            now = datetime.now(timezone.utc)
            rows = pd.DataFrame({
                "trip_id": ["old", "new"],
                "arrival_delay": [10, 20],
                "fetched_at": [(now - timedelta(minutes=30)).isoformat(), now.isoformat()],
            })
            rows.to_sql("trip_updates", engine, if_exists="append", index=False)

            recent = read_recent(engine, "trip_updates", now - timedelta(minutes=20))
            engine.dispose()

        self.assertEqual(recent["trip_id"].tolist(), ["new"])


class PredictLiveTest(unittest.TestCase):
    def test_predicts_each_live_trains_newest_minute_only(self):
        newest = pd.Timestamp("2026-10-02 10:10", tz="UTC")
        features = pd.DataFrame({
            "trip_id": ["A", "A", "B", "C"],
            "route_id": "R1",
            "window_start": [newest - pd.Timedelta(minutes=1), newest, newest, newest - pd.Timedelta(minutes=10)],
            "stop_id": "S1",
            "stop_sequence": 3,
            "arrival_delay": [5.0, 7.0, -3.0, 40.0],
        })

        class AddTen:
            def predict(self, X):
                return X["arrival_delay"].to_numpy() + 10

        with mock.patch("src.orchestration.pipeline.build_features", return_value=features), \
                mock.patch("src.orchestration.pipeline.read_recent", return_value=pd.DataFrame()), \
                mock.patch("src.orchestration.pipeline.load_feature_columns", return_value=["arrival_delay"]), \
                mock.patch("src.orchestration.pipeline.load_model", return_value=AddTen()):
            out = predict_live(engine=None).set_index("trip_id")

        self.assertEqual(sorted(out.index), ["A", "B"])
        self.assertEqual(out.loc["A", "arrival_delay"], 7.0)
        self.assertEqual(out.loc["A", "predicted_delay_15min"], 17.0)
        self.assertEqual(out.loc["B", "predicted_delay_5min"], 7.0)


class RunOncePredictTest(unittest.TestCase):
    def _run(self, predict_live_mock):
        empty = pd.DataFrame()
        with mock.patch("src.orchestration.pipeline.get_engine"), \
                mock.patch("src.orchestration.pipeline.init_db"), \
                mock.patch("src.orchestration.pipeline.fetch_trip_updates"), \
                mock.patch("src.orchestration.pipeline.fetch_vehicle_positions"), \
                mock.patch("src.orchestration.pipeline.fetch_alerts"), \
                mock.patch("src.orchestration.pipeline.decode_trip_updates", return_value=empty), \
                mock.patch("src.orchestration.pipeline.decode_vehicle_positions", return_value=empty), \
                mock.patch("src.orchestration.pipeline.decode_alerts", return_value=empty), \
                mock.patch("src.orchestration.pipeline.write_trip_updates"), \
                mock.patch("src.orchestration.pipeline.write_vehicle_positions"), \
                mock.patch("src.orchestration.pipeline.write_alerts"), \
                mock.patch("src.orchestration.pipeline.predict_live", predict_live_mock), \
                mock.patch("src.orchestration.pipeline.write_predictions") as write:
            run_once(predict=True)
        return write

    def test_no_live_trains_writes_nothing(self):
        write = self._run(mock.Mock(return_value=pd.DataFrame()))
        write.assert_not_called()

    def test_a_prediction_error_does_not_stop_the_cycle(self):
        write = self._run(mock.Mock(side_effect=ValueError("bad row")))
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
