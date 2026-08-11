import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from vaultwares_adk.telemetry import configure, get_config
from vaultwares_adk.telemetry.record import RunRecord, build_batch, utc_now
from vaultwares_adk.telemetry.runs import ModelRun, usage_from_openai
from vaultwares_adk.telemetry.spool import deliver, spool_backlog
from vaultwares_adk.telemetry.worker import RunWorker


def _isolated_spool():
    """Point the recorder at a temp spool and a dead API so deliver() spools.

    Config is process-global, so this restores every field a test might have
    changed — otherwise a test that shrinks queue_max makes a later, unrelated
    test fail with a confusing queue.Full.
    """
    return configure(
        spool_dir=tempfile.mkdtemp(prefix="vw-telemetry-test"),
        api_url="http://127.0.0.1:9",
        post_timeout_s=0.15,
        enabled=True,
        queue_max=10000,
        batch_max=200,
        send_raw_runs=True,
        capture_prompt_text=False,
        public_surface=False,
    )


class TestRunRecordFinalize(unittest.TestCase):
    def test_derives_duration_ttft_and_totals(self):
        start = utc_now()
        record = RunRecord(
            provider="huggingface",
            runtime="hf-inference",
            model="m",
            started_at=start,
            first_token_at=start + timedelta(milliseconds=200),
            ended_at=start + timedelta(milliseconds=1200),
            input_tokens=100,
            output_tokens=500,
        )
        record.finalize()
        self.assertAlmostEqual(record.duration_ms, 1200.0, places=1)
        self.assertAlmostEqual(record.ttft_ms, 200.0, places=1)
        self.assertEqual(record.total_tokens, 600)

    def test_throughput_measures_decode_not_total_wall_time(self):
        # 500 tokens over a 1000 ms decode window = 500 tok/s. Measuring across
        # the full 1200 ms (including prefill) would understate it at ~417.
        start = utc_now()
        record = RunRecord(
            provider="p",
            runtime="r",
            model="m",
            started_at=start,
            first_token_at=start + timedelta(milliseconds=200),
            ended_at=start + timedelta(milliseconds=1200),
            output_tokens=500,
        ).finalize()
        self.assertAlmostEqual(record.tokens_per_second, 500.0, places=1)

    def test_queue_time_split_from_service_time(self):
        queued = utc_now()
        record = RunRecord(
            provider="p",
            runtime="r",
            model="m",
            queued_at=queued,
            started_at=queued + timedelta(milliseconds=350),
            ended_at=queued + timedelta(milliseconds=1350),
        ).finalize()
        self.assertAlmostEqual(record.queue_ms, 350.0, places=1)
        self.assertAlmostEqual(record.duration_ms, 1000.0, places=1)

    def test_unknown_status_is_forced_terminal(self):
        record = RunRecord(provider="p", runtime="r", model="m", status="weird").finalize()
        self.assertEqual(record.status, "error")

    def test_to_json_drops_nulls_and_stamps_iso(self):
        record = RunRecord(provider="p", runtime="r", model="m").finalize()
        payload = record.to_json()
        self.assertNotIn("cost_usd", payload)  # unset -> omitted
        self.assertTrue(payload["ended_at"].endswith("Z"))
        self.assertNotIn("extra", payload)  # empty dict -> omitted

    def test_finalize_is_idempotent(self):
        record = RunRecord(provider="p", runtime="r", model="m", output_tokens=10).finalize()
        first = record.to_json()
        self.assertEqual(record.finalize().to_json(), first)


class TestModelRun(unittest.TestCase):
    def setUp(self):
        _isolated_spool()

    def test_first_token_only_counts_once(self):
        with ModelRun(provider="p", runtime="r", model="m") as run:
            run.first_token()
            stamped = run.record.first_token_at
            run.first_token()
            self.assertEqual(run.record.first_token_at, stamped)

    def test_exception_is_recorded_then_reraised(self):
        run_ref = {}
        with self.assertRaises(ValueError):
            with ModelRun(provider="p", runtime="r", model="m") as run:
                run_ref["r"] = run
                raise ValueError("boom")
        record = run_ref["r"].record
        self.assertEqual(record.status, "error")
        self.assertEqual(record.error_class, "ValueError")
        self.assertEqual(record.error_message, "boom")

    def test_timeout_classified_apart_from_error(self):
        with self.assertRaises(TimeoutError):
            with ModelRun(provider="p", runtime="r", model="m") as run:
                raise TimeoutError("stalled")
        self.assertEqual(run.record.status, "timeout")

    def test_reject_is_not_an_error(self):
        # A budget-guard stop is a policy outcome; counting it as a fault would
        # make the failure-rate widget blame the model for a spending cap.
        with ModelRun(provider="p", runtime="r", model="m") as run:
            run.reject("monthly HF credits exhausted")
        self.assertEqual(run.record.status, "rejected")
        self.assertEqual(run.record.error_class, "BudgetRejected")

    def test_prompt_records_shape_only_by_default(self):
        # Neither the text nor a hash of it. See TestPrivacyContract for why a
        # hash is not an acceptable default.
        configure(capture_prompt_text=False)
        with ModelRun(provider="p", runtime="r", model="m") as run:
            run.prompt("secret internal prompt")
        self.assertEqual(run.record.prompt_chars, 22)
        self.assertIsNone(run.record.prompt_hash)
        self.assertNotIn("prompt_text", run.record.extra)

    def test_unknown_kwargs_land_in_extra(self):
        with ModelRun(provider="p", runtime="r", model="m", tenant="vaultwares") as run:
            run.set(steps=28, custom_flag=True)
        self.assertEqual(run.record.steps, 28)  # known column
        self.assertEqual(run.record.extra["tenant"], "vaultwares")
        self.assertTrue(run.record.extra["custom_flag"])

    def test_usage_from_openai_dict_response(self):
        with ModelRun(provider="p", runtime="r", model="m") as run:
            usage_from_openai(
                run,
                {
                    "usage": {
                        "prompt_tokens": 30,
                        "completion_tokens": 70,
                        "total_tokens": 100,
                        "prompt_tokens_details": {"cached_tokens": 12},
                    },
                    "choices": [{"finish_reason": "stop"}],
                },
            )
        self.assertEqual(run.record.input_tokens, 30)
        self.assertEqual(run.record.cached_input_tokens, 12)
        self.assertEqual(run.record.finish_reason, "stop")


class TestSpoolTransport(unittest.TestCase):
    def setUp(self):
        self.config = _isolated_spool()

    def test_deliver_falls_back_to_spool_when_api_is_down(self):
        batch = build_batch([RunRecord(provider="p", runtime="r", model="m").finalize()],
                            host="h", source="test", batch_index=1)
        self.assertEqual(deliver(batch, self.config), "spooled")
        backlog = spool_backlog(self.config)
        self.assertEqual(backlog["batches"], 1)

    def test_spool_file_is_one_whole_batch_per_line(self):
        # drain-spool.ps1 POSTs each line verbatim, so a line must be a
        # complete batch object, not a single run.
        for index in range(3):
            deliver(
                build_batch([RunRecord(provider="p", runtime="r", model="m").finalize()],
                            host="h", source="test", batch_index=index),
                self.config,
            )
        files = list(Path(self.config.spool_dir).glob("*.jsonl"))
        self.assertEqual(len(files), 1)
        lines = [l for l in files[0].read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lines), 3)
        for line in lines:
            payload = json.loads(line)
            self.assertIn("runs", payload)
            self.assertIn("host", payload)


class TestWorker(unittest.TestCase):
    def setUp(self):
        self.config = _isolated_spool()

    def test_drain_moves_runs_off_the_queue_without_network(self):
        # Draining is the crash-safety cadence and must do no I/O: runs land in
        # the rollup and the pending buffer, nothing is delivered yet.
        worker = RunWorker()
        for _ in range(5):
            worker._queue.put_nowait(
                RunRecord(provider="p", runtime="r", model="m", started_at=utc_now())
            )
        worker._drain_once(self.config)
        stats = worker.stats()
        self.assertEqual(stats["drained"], 5)
        self.assertEqual(stats["queue_depth"], 0)
        self.assertEqual(stats["pending_runs"], 5)
        self.assertEqual(stats["posted"] + stats["spooled"], 0)

    def test_send_delivers_pending_runs(self):
        worker = RunWorker()
        for _ in range(5):
            worker._queue.put_nowait(
                RunRecord(provider="p", runtime="r", model="m", started_at=utc_now())
            )
        worker._drain_once(self.config)
        worker._send_once(self.config, final=True)
        stats = worker.stats()
        self.assertEqual(stats["spooled"], 5)
        self.assertEqual(stats["pending_runs"], 0)

    def test_open_hour_is_held_back_until_it_closes(self):
        # Only complete hours are shipped, so a rollup row is final when it
        # arrives and a replay can overwrite rather than double-count.
        worker = RunWorker()
        worker._queue.put_nowait(
            RunRecord(provider="p", runtime="r", model="m", started_at=utc_now())
        )
        worker._drain_once(self.config)
        worker._send_once(self.config)  # not final
        self.assertEqual(worker.stats()["open_buckets"], 1)
        self.assertEqual(worker.stats().get("rollups_spooled", 0), 0)

    def test_shutdown_flushes_the_partial_hour(self):
        worker = RunWorker()
        worker._queue.put_nowait(
            RunRecord(provider="p", runtime="r", model="m", started_at=utc_now())
        )
        worker._drain_once(self.config)
        worker._send_once(self.config, final=True)
        self.assertEqual(worker.stats()["open_buckets"], 0)
        self.assertEqual(worker.stats()["rollups_spooled"], 1)

    def test_queue_overflow_sheds_instead_of_raising(self):
        configure(queue_max=2)
        worker = RunWorker()
        for _ in range(6):
            worker.record(RunRecord(provider="p", runtime="r", model="m"))
        # Whatever the split, recording must never raise and must be accounted
        # for in one of the two counters.
        stats = worker.stats()
        self.assertEqual(stats["queued"] + stats["overflow"], 6)

    def test_disabled_recorder_is_a_no_op(self):
        configure(enabled=False)
        worker = RunWorker()
        worker.record(RunRecord(provider="p", runtime="r", model="m"))
        self.assertEqual(worker.stats()["queued"], 0)
        configure(enabled=True)


if __name__ == "__main__":
    unittest.main()


class TestPrivacyContract(unittest.TestCase):
    """Rules from vault-inference/docs/hf-telemetry-design.md.

    These are the assertions that keep a public HF Space from turning into an
    exfiltration path pointed at our own API.
    """

    def setUp(self):
        _isolated_spool()

    def tearDown(self):
        configure(capture_prompt_text=False, public_surface=False)

    def test_prompt_hash_is_off_by_default(self):
        # A hash is not a safe middle ground: it still correlates one user
        # across every record they appear in.
        configure(capture_prompt_text=False)
        with ModelRun(provider="p", runtime="r", model="m") as run:
            run.prompt("who is my doctor")
        self.assertIsNone(run.record.prompt_hash)
        self.assertEqual(run.record.prompt_chars, 16)

    def test_prompt_text_never_reaches_the_wire(self):
        configure(capture_prompt_text=True)  # even fully opted in
        with ModelRun(provider="p", runtime="r", model="m") as run:
            run.prompt("secret")
        payload = json.dumps(run.record.finalize().to_json())
        self.assertNotIn("secret", payload)

    def test_public_surface_strips_internal_estate(self):
        record = RunRecord(
            provider="huggingface", runtime="hf-space", model="m",
            host="Clopeux-Desktop", project="vaultwares-studio",
            service="pro-realism", session_id="visitor-42",
            caller="app.generate", gpu_name="RTX 3060",
            prompt_hash="deadbeef",
        ).finalize()
        public = record.to_json(public_surface=True)
        for banned in ("host", "project", "service", "session_id", "caller",
                       "gpu_name", "prompt_hash"):
            self.assertNotIn(banned, public, f"{banned} leaked from a public surface")
        # The useful, non-identifying fields must still survive.
        self.assertEqual(public["model"], "m")
        self.assertEqual(public["provider"], "huggingface")

    def test_public_batch_envelope_hides_the_hostname(self):
        batch = build_batch(
            [RunRecord(provider="p", runtime="r", model="m").finalize()],
            host="Clopeux-Desktop",
            source="hf-space-personaplex",
            batch_index=1,
            public_surface=True,
        )
        self.assertNotIn("Clopeux-Desktop", json.dumps(batch))
        self.assertTrue(batch["publicSurface"])
        self.assertNotIn("agent", batch)  # pid/platform describe our estate

    def test_private_batch_keeps_attribution(self):
        batch = build_batch(
            [RunRecord(provider="p", runtime="r", model="m", project="vault-inference").finalize()],
            host="Clopeux-Desktop", source="vw-ai-runs", batch_index=1,
        )
        self.assertEqual(batch["host"], "Clopeux-Desktop")
        self.assertEqual(batch["runs"][0]["project"], "vault-inference")

    def test_allowlist_is_closed_not_open(self):
        # A field nobody has reviewed must not ship from a public surface just
        # because it was added to the record.
        record = RunRecord(provider="p", runtime="r", model="m")
        record.extra["brand_new_kpi"] = "value"
        public = record.finalize().to_json(public_surface=True)
        self.assertNotIn("extra", public)
        self.assertNotIn("brand_new_kpi", json.dumps(public))


class TestPollerRecords(unittest.TestCase):
    """Pollers observe finished work, so they report a duration and no start."""

    def setUp(self):
        _isolated_spool()

    def test_started_at_is_backfilled_from_duration(self):
        # A NULL started_at is invisible to every time-windowed query over
        # ai_runs while the hourly rollup still counts it, so the two grains
        # would disagree about how much ran.
        record = RunRecord(
            provider="comfyui", runtime="comfyui", model="flux2-klein",
            duration_ms=8000.0,
        ).finalize()
        self.assertIsNotNone(record.started_at)
        delta = (record.ended_at - record.started_at).total_seconds()
        self.assertAlmostEqual(delta, 8.0, places=2)

    def test_started_at_falls_back_to_ended_at_without_a_duration(self):
        record = RunRecord(provider="ollama", runtime="ollama", model="m").finalize()
        self.assertEqual(record.started_at, record.ended_at)

    def test_an_explicit_start_is_never_overwritten(self):
        start = utc_now() - timedelta(seconds=30)
        record = RunRecord(
            provider="p", runtime="r", model="m",
            started_at=start, duration_ms=1000.0,
        ).finalize()
        self.assertEqual(record.started_at, start)

    def test_poller_record_reaches_the_rollup_and_the_raw_row_alike(self):
        from vaultwares_adk.telemetry.rollup import RollupAggregator

        record = RunRecord(
            provider="comfyui", runtime="comfyui", model="flux2-klein",
            duration_ms=8000.0,
        ).finalize()
        agg = RollupAggregator()
        agg.add(record)
        self.assertEqual(agg.stats()["open_buckets"], 1)
        self.assertIn("started_at", record.to_json())

