import unittest
from datetime import datetime, timedelta, timezone

from vaultwares_adk.telemetry.record import RunRecord
from vaultwares_adk.telemetry.rollup import (
    DURATION_EDGES_MS,
    RollupAggregator,
    build_rollup_batch,
    hour_floor,
    percentile_from_hist,
)


def _run(**overrides):
    base = dict(
        provider="huggingface",
        runtime="hf-inference",
        model="Qwen/Qwen3.6-35B",
        task="chat",
        project="vault-inference",
        host="Clopeux-Desktop",
        status="ok",
        started_at=datetime(2026, 8, 10, 14, 30, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return RunRecord(**base).finalize()


class TestBucketing(unittest.TestCase):
    def test_runs_in_the_same_hour_and_shape_share_a_bucket(self):
        agg = RollupAggregator()
        for _ in range(3):
            agg.add(_run(duration_ms=100.0))
        self.assertEqual(agg.stats()["open_buckets"], 1)

    def test_different_status_splits_the_bucket(self):
        # Otherwise a failure rate cannot be recovered from the rollup.
        agg = RollupAggregator()
        agg.add(_run(status="ok"))
        agg.add(_run(status="error"))
        self.assertEqual(agg.stats()["open_buckets"], 2)

    def test_different_hour_splits_the_bucket(self):
        agg = RollupAggregator()
        agg.add(_run(started_at=datetime(2026, 8, 10, 14, 59, tzinfo=timezone.utc)))
        agg.add(_run(started_at=datetime(2026, 8, 10, 15, 1, tzinfo=timezone.utc)))
        self.assertEqual(agg.stats()["open_buckets"], 2)

    def test_hour_floor_truncates_not_rounds(self):
        moment = datetime(2026, 8, 10, 14, 59, 59, tzinfo=timezone.utc)
        self.assertEqual(hour_floor(moment).hour, 14)

    def test_a_run_with_no_timestamp_is_skipped_not_misfiled(self):
        agg = RollupAggregator()
        agg.add(RunRecord(provider="p", runtime="r", model="m", started_at=None, ended_at=None))
        self.assertEqual(agg.stats()["open_buckets"], 0)

    def test_cardinality_is_capped(self):
        agg = RollupAggregator(max_buckets=3)
        for i in range(10):
            agg.add(_run(model=f"model-{i}"))
        self.assertEqual(agg.stats()["open_buckets"], 3)
        self.assertEqual(agg.stats()["dropped_buckets"], 7)


class TestAccumulation(unittest.TestCase):
    def _single(self, agg):
        buckets = agg.take_all()
        self.assertEqual(len(buckets), 1)
        return buckets[0].to_json()

    def test_tokens_and_cost_sum(self):
        agg = RollupAggregator()
        agg.add(_run(input_tokens=100, output_tokens=200, cost_usd=0.001))
        agg.add(_run(input_tokens=50, output_tokens=25, cost_usd=0.002))
        out = self._single(agg)
        self.assertEqual(out["runs"], 2)
        self.assertEqual(out["input_tokens"], 150)
        self.assertEqual(out["output_tokens"], 225)
        self.assertAlmostEqual(out["cost_usd"], 0.003, places=9)

    def test_provisional_cost_is_kept_apart_from_settled(self):
        # A provisional cost is a placeholder zero-or-guess; adding it into the
        # settled total would make spend look real before it is.
        agg = RollupAggregator()
        agg.add(_run(cost_usd=0.005, cost_state="settled"))
        agg.add(_run(cost_usd=0.009, cost_state="provisional"))
        out = self._single(agg)
        self.assertAlmostEqual(out["cost_usd"], 0.005, places=9)
        self.assertAlmostEqual(out["cost_usd_provisional"], 0.009, places=9)

    def test_missing_ttft_stays_out_of_the_denominator(self):
        # A run that never streamed must not drag the average TTFT toward zero.
        agg = RollupAggregator()
        agg.add(_run(ttft_ms=200.0))
        agg.add(_run(ttft_ms=400.0))
        agg.add(_run())  # no ttft at all
        out = self._single(agg)
        self.assertEqual(out["ttft_ms_count"], 2)
        self.assertAlmostEqual(out["ttft_ms_sum"] / out["ttft_ms_count"], 300.0, places=6)

    def test_policy_outcomes_are_not_failures(self):
        agg = RollupAggregator()
        for status in ("error", "timeout", "rejected", "cancelled", "ok"):
            agg.add(_run(status=status))
        total = sum(b.failures for b in agg.take_all())
        self.assertEqual(total, 2)  # error + timeout only

    def test_min_and_max_track_extremes(self):
        agg = RollupAggregator()
        for d in (500.0, 50.0, 9000.0):
            agg.add(_run(duration_ms=d))
        out = self._single(agg)
        self.assertEqual(out["duration_ms_min"], 50.0)
        self.assertEqual(out["duration_ms_max"], 9000.0)

    def test_null_gpu_fields_are_omitted_not_zeroed(self):
        agg = RollupAggregator()
        agg.add(_run())
        out = self._single(agg)
        self.assertNotIn("vram_peak_mb_max", out)


class TestHistogram(unittest.TestCase):
    def test_durations_land_in_the_right_bucket(self):
        agg = RollupAggregator()
        agg.add(_run(duration_ms=10.0))      # 0-50
        agg.add(_run(duration_ms=75.0))      # 50-100
        agg.add(_run(duration_ms=1500.0))    # 1000-2500
        hist = agg.take_all()[0].duration_hist
        self.assertEqual(hist[0], 1)
        self.assertEqual(hist[1], 1)
        self.assertEqual(hist[DURATION_EDGES_MS.index(1000)], 1)

    def test_value_above_the_last_edge_lands_in_the_final_bucket(self):
        agg = RollupAggregator()
        agg.add(_run(duration_ms=999_999.0))
        hist = agg.take_all()[0].duration_hist
        self.assertEqual(hist[-1], 1)

    def test_histograms_merge_by_addition(self):
        # The whole reason for a histogram instead of a percentile: two hosts'
        # buckets for the same hour must combine exactly.
        a, b = RollupAggregator(), RollupAggregator()
        for _ in range(3):
            a.add(_run(duration_ms=100.0))
        for _ in range(2):
            b.add(_run(duration_ms=100.0))
        ha = a.take_all()[0].duration_hist
        hb = b.take_all()[0].duration_hist
        merged = [x + y for x, y in zip(ha, hb)]
        self.assertEqual(sum(merged), 5)

    def test_percentile_is_within_its_bucket(self):
        hist = [0] * len(DURATION_EDGES_MS)
        hist[DURATION_EDGES_MS.index(500)] = 100  # all runs in 500-1000ms
        p50 = percentile_from_hist(hist, 0.5)
        self.assertGreaterEqual(p50, 500)
        self.assertLessEqual(p50, 1000)

    def test_percentile_of_empty_histogram_is_none(self):
        self.assertIsNone(percentile_from_hist([0] * len(DURATION_EDGES_MS), 0.95))

    def test_p95_lands_in_the_slow_tail_when_the_tail_is_big_enough(self):
        # 90 fast + 10 slow: the 95th of 100 sorted values is a slow one.
        hist = [0] * len(DURATION_EDGES_MS)
        hist[0] = 90
        hist[len(hist) - 2] = 10
        self.assertGreater(percentile_from_hist(hist, 0.95), 1000)

    def test_p95_stays_fast_when_the_tail_is_below_five_percent(self):
        # 95 fast + 5 slow: the 95th value is still a fast one, so a p95 in the
        # tail would be wrong. Guards against an off-by-one at the boundary.
        hist = [0] * len(DURATION_EDGES_MS)
        hist[0] = 95
        hist[len(hist) - 2] = 5
        self.assertLessEqual(percentile_from_hist(hist, 0.95), 50)
        # ...but p99 must find the tail.
        self.assertGreater(percentile_from_hist(hist, 0.99), 1000)


class TestClosing(unittest.TestCase):
    def test_take_closed_holds_back_the_current_hour(self):
        agg = RollupAggregator()
        now = datetime(2026, 8, 10, 15, 5, tzinfo=timezone.utc)
        agg.add(_run(started_at=now - timedelta(hours=2)))
        agg.add(_run(started_at=now))
        closed = agg.take_closed(now=now)
        self.assertEqual(len(closed), 1)
        self.assertEqual(agg.stats()["open_buckets"], 1)

    def test_take_closed_removes_what_it_returns(self):
        # A bucket returned twice would double-count on the second send.
        agg = RollupAggregator()
        now = datetime(2026, 8, 10, 15, 5, tzinfo=timezone.utc)
        agg.add(_run(started_at=now - timedelta(hours=1)))
        self.assertEqual(len(agg.take_closed(now=now)), 1)
        self.assertEqual(len(agg.take_closed(now=now)), 0)

    def test_batch_envelope_declares_the_grain(self):
        agg = RollupAggregator()
        agg.add(_run())
        batch = build_rollup_batch(agg.take_all(), host="h", source="s", batch_index=1)
        self.assertEqual(batch["grain"], "hour")
        self.assertEqual(len(batch["rollups"]), 1)
        self.assertTrue(batch["rollups"][0]["hour"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
