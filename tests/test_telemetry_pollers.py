import tempfile
import unittest

from vaultwares_adk.telemetry import configure
from vaultwares_adk.telemetry.pollers import comfyui, ollama
from vaultwares_adk.telemetry.pollers.runner import PollerLoop, poll_once


def _isolated():
    return configure(
        spool_dir=tempfile.mkdtemp(prefix="vw-poller-test"),
        api_url="http://127.0.0.1:9",
        post_timeout_s=0.15,
        enabled=True,
        queue_max=10000,
    )


# Shape taken from a real Ollama /api/chat response. All durations nanoseconds.
OLLAMA_RESPONSE = {
    "model": "qwen3-vl:2b",
    "created_at": "2026-08-11T01:20:00Z",
    "message": {"role": "assistant", "content": "hello"},
    "done": True,
    "done_reason": "stop",
    "total_duration": 3_500_000_000,
    "load_duration": 800_000_000,
    "prompt_eval_count": 26,
    "prompt_eval_duration": 200_000_000,
    "eval_count": 290,
    "eval_duration": 2_500_000_000,
}


class TestOllamaMetrics(unittest.TestCase):
    def setUp(self):
        _isolated()

    def test_nanoseconds_become_milliseconds(self):
        m = ollama.metrics_from_response(OLLAMA_RESPONSE)
        self.assertAlmostEqual(m["duration_ms"], 3500.0, places=1)
        self.assertAlmostEqual(m["load_ms"], 800.0, places=1)

    def test_ttft_is_load_plus_prompt_eval(self):
        # Everything before the first output token can be emitted, which is
        # what TTFT means for every other backend.
        m = ollama.metrics_from_response(OLLAMA_RESPONSE)
        self.assertAlmostEqual(m["ttft_ms"], 1000.0, places=1)

    def test_throughput_excludes_model_load(self):
        # 290 tokens / 2.5s decode = 116 tok/s. Charging the 0.8s cold load
        # against decode speed would report ~83 and make every first call to a
        # model look slow.
        m = ollama.metrics_from_response(OLLAMA_RESPONSE)
        self.assertAlmostEqual(m["tokens_per_second"], 116.0, places=1)

    def test_token_counts_map_to_input_and_output(self):
        m = ollama.metrics_from_response(OLLAMA_RESPONSE)
        self.assertEqual(m["input_tokens"], 26)
        self.assertEqual(m["output_tokens"], 290)

    def test_missing_fields_are_omitted_not_zeroed(self):
        m = ollama.metrics_from_response({"model": "m", "done": True})
        self.assertNotIn("duration_ms", m)
        self.assertNotIn("tokens_per_second", m)
        self.assertEqual(m["model"], "m")

    def test_zero_eval_duration_does_not_divide_by_zero(self):
        m = ollama.metrics_from_response(
            {"model": "m", "eval_count": 10, "eval_duration": 0}
        )
        self.assertNotIn("tokens_per_second", m)

    def test_record_response_marks_local_runs_free(self):
        record = ollama.record_response(OLLAMA_RESPONSE, project="vault-monitor")
        self.assertEqual(record.provider, "ollama")
        self.assertEqual(record.cost_usd, 0.0)
        self.assertTrue(record.is_free)
        self.assertEqual(record.output_tokens, 290)


# Shape taken from ComfyUI /history. Timestamps are epoch milliseconds.
COMFY_ENTRY = {
    "prompt": [
        0,
        "abc-123",
        {
            "4": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": "flux2-klein.safetensors"}},
            "5": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            "3": {"class_type": "KSampler",
                  "inputs": {"steps": 28, "cfg": 4.5, "sampler_name": "euler",
                             "scheduler": "normal", "seed": 12345,
                             "model": ["4", 0]}},
            "10": {"class_type": "LoraLoader", "inputs": {"lora_name": "a.safetensors"}},
            "11": {"class_type": "LoraLoader", "inputs": {"lora_name": "b.safetensors"}},
        },
        {},
        [],
    ],
    "outputs": {"9": {"images": [{"filename": "x.png"}, {"filename": "y.png"}]}},
    "status": {
        "status_str": "success",
        "completed": True,
        "messages": [
            ["execution_start", {"prompt_id": "abc-123", "timestamp": 1_000_000}],
            ["execution_success", {"prompt_id": "abc-123", "timestamp": 1_008_500}],
        ],
    },
}


class TestComfyHistory(unittest.TestCase):
    def setUp(self):
        _isolated()

    def test_run_id_is_deterministic_for_dedupe(self):
        # /history returns everything every poll, so the id must be stable:
        # that is what makes a resend a no-op at the API.
        self.assertEqual(comfyui.run_id_for("abc-123"), comfyui.run_id_for("abc-123"))
        self.assertNotEqual(comfyui.run_id_for("abc-123"), comfyui.run_id_for("abc-124"))

    def test_duration_comes_from_execution_timestamps(self):
        record = comfyui.record_from_history_entry("abc-123", COMFY_ENTRY)
        self.assertAlmostEqual(record.duration_ms, 8500.0, places=1)

    def test_graph_metrics_are_extracted(self):
        record = comfyui.record_from_history_entry("abc-123", COMFY_ENTRY)
        self.assertEqual(record.model, "flux2-klein.safetensors")
        self.assertEqual(record.steps, 28)
        self.assertEqual(record.sampler, "euler")
        self.assertEqual(record.cfg_scale, 4.5)
        self.assertEqual(record.width, 1024)
        self.assertEqual(record.lora_count, 2)

    def test_wired_inputs_are_not_mistaken_for_values(self):
        # A wired input arrives as ["node_id", slot]; recording that as a
        # sampler value would put a list in a scalar column.
        record = comfyui.record_from_history_entry("abc-123", COMFY_ENTRY)
        self.assertNotIsInstance(record.extra.get("model_input"), list)
        self.assertIsInstance(record.steps, int)

    def test_output_images_are_counted(self):
        record = comfyui.record_from_history_entry("abc-123", COMFY_ENTRY)
        self.assertEqual(record.image_count, 2)

    def test_error_status_is_classified(self):
        entry = dict(COMFY_ENTRY)
        entry["status"] = {
            "status_str": "error", "completed": True,
            "messages": [["execution_start", {"timestamp": 1_000_000}],
                         ["execution_error", {"timestamp": 1_002_000}]],
        }
        record = comfyui.record_from_history_entry("err-1", entry)
        self.assertEqual(record.status, "error")
        self.assertEqual(record.error_class, "ComfyExecutionError")
        self.assertAlmostEqual(record.duration_ms, 2000.0, places=1)

    def test_interrupted_job_is_cancelled_not_failed(self):
        entry = dict(COMFY_ENTRY)
        entry["status"] = {"status_str": "interrupted", "completed": True, "messages": []}
        record = comfyui.record_from_history_entry("int-1", entry)
        self.assertEqual(record.status, "cancelled")

    def test_still_running_entry_is_skipped(self):
        entry = {"prompt": [0, "p", {}, {}, []], "status": {"completed": False}}
        self.assertIsNone(comfyui.record_from_history_entry("p", entry))

    def test_malformed_entry_does_not_raise(self):
        # Third-party API: a schema change should cost a field, not a crash.
        record = comfyui.record_from_history_entry(
            "weird", {"prompt": "not-a-list", "status": {"status_str": "success"}}
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.model, "unknown")

    def test_missing_timestamps_leave_duration_unset(self):
        entry = dict(COMFY_ENTRY)
        entry["status"] = {"status_str": "success", "completed": True, "messages": []}
        record = comfyui.record_from_history_entry("no-ts", entry)
        # finalize() backfills started_at, but an invented duration would be a
        # measurement we never made.
        self.assertEqual(record.duration_ms, 0.0)


class TestRunner(unittest.TestCase):
    def setUp(self):
        _isolated()

    def test_a_down_runtime_is_a_skipped_cycle_not_an_error(self):
        # ComfyUI is frequently not running; that must not crash-loop the poller.
        counts = poll_once(
            comfyui_url="http://127.0.0.1:9",
            ollama_url="http://127.0.0.1:9",
        )
        self.assertEqual(counts["comfyui_runs"], 0)
        self.assertEqual(counts["ollama_residency"], 0)

    def test_disabled_pollers_are_skipped(self):
        counts = poll_once(comfyui_url=None, ollama_url=None)
        self.assertEqual(counts, {"comfyui_runs": 0, "ollama_residency": 0, "errors": 0})

    def test_seen_cursor_suppresses_repeat_records(self):
        seen = {"abc-123"}
        records = []
        original = comfyui.fetch_history
        comfyui.fetch_history = lambda *a, **k: {"abc-123": COMFY_ENTRY}
        try:
            records = comfyui.poll_history("http://x", seen=seen)
        finally:
            comfyui.fetch_history = original
        self.assertEqual(records, [])

    def test_loop_bounds_its_seen_set(self):
        loop = PollerLoop(max_seen=3, comfyui_url=None, ollama_url=None)
        loop._seen.update({"a", "b", "c", "d"})
        loop.poll()
        self.assertLessEqual(len(loop._seen), 3)


if __name__ == "__main__":
    unittest.main()
