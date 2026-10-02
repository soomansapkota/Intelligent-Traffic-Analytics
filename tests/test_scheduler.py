import unittest
from unittest import mock

from src.orchestration.scheduler import run_forever


class RunForeverTest(unittest.TestCase):
    def test_zero_duration_still_runs_one_cycle(self):
        with mock.patch("src.orchestration.scheduler.run_once") as run, mock.patch("time.sleep") as sleep:
            run_forever(duration_minutes=0)
        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()

    def test_runs_until_deadline_then_stops(self):
        clock = iter([0, 10, 20, 30, 40, 50, 60, 70])
        with mock.patch("src.orchestration.scheduler.run_once") as run, \
             mock.patch("time.sleep"), \
             mock.patch("time.monotonic", side_effect=lambda: next(clock)):
            run_forever(interval_seconds=15, duration_minutes=0.5)
        self.assertEqual(run.call_count, 3)

    def test_interval_floor_protects_the_api(self):
        clock = iter([0, 10, 20, 30])
        with mock.patch("src.orchestration.scheduler.run_once"), \
             mock.patch("time.sleep") as sleep, \
             mock.patch("time.monotonic", side_effect=lambda: next(clock)):
            run_forever(interval_seconds=1, duration_minutes=0.5)
        self.assertEqual({call.args[0] for call in sleep.call_args_list}, {15})

    def test_keyboard_interrupt_exits_cleanly(self):
        with mock.patch("src.orchestration.scheduler.run_once", side_effect=KeyboardInterrupt), mock.patch("time.sleep"):
            run_forever(duration_minutes=5)

    def test_publish_flag_is_passed_through(self):
        with mock.patch("src.orchestration.scheduler.run_once") as run, mock.patch("time.sleep"):
            run_forever(duration_minutes=0, publish=True)
        run.assert_called_once_with(publish=True)


if __name__ == "__main__":
    unittest.main()
