"""
Unit tests for RedisCoordinator.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import time

# Mock redis before importing RedisCoordinator
mock_redis = MagicMock()
sys.modules['redis'] = mock_redis

# Force reload or ensure it's imported after mocking
if 'redis_coordinator' in sys.modules:
    import importlib
    import redis_coordinator
    importlib.reload(redis_coordinator)
else:
    import redis_coordinator

class TestRedisCoordinator(unittest.TestCase):
    def setUp(self):
        # Reset mock before each test
        mock_redis.reset_mock()

        # Configure the Redis client mock
        self.mock_r = MagicMock()
        mock_redis.Redis.return_value = self.mock_r

        # Configure pubsub mock
        self.mock_pubsub = MagicMock()
        self.mock_r.pubsub.return_value = self.mock_pubsub

        # Ensure redis_coordinator.redis is the mock
        redis_coordinator.redis = mock_redis

        self.coordinator = redis_coordinator.RedisCoordinator(
            agent_id="test-agent",
            channel="test-channel"
        )

    def test_init(self):
        """Verify initialization sets correct attributes and subscribes to channel."""
        self.assertEqual(self.coordinator.agent_id, "test-agent")
        self.assertEqual(self.coordinator.channel, "test-channel")
        self.mock_r.pubsub.assert_called_once()
        self.mock_pubsub.subscribe.assert_called_once_with("test-channel")

    def test_publish(self):
        """Verify publish sends correctly formatted JSON to the correct channel."""
        action = "test-action"
        task = "test-task"
        details = {"foo": "bar"}

        self.coordinator.publish(action, task, details)

        # Verify publish call
        self.mock_r.publish.assert_called_once()
        args, _ = self.mock_r.publish.call_args
        self.assertEqual(args[0], "test-channel")

        # Verify JSON payload
        payload = json.loads(args[1])
        self.assertEqual(payload['agent'], "test-agent")
        self.assertEqual(payload['action'], action)
        self.assertEqual(payload['task'], task)
        self.assertEqual(payload['details'], details)

    def test_publish_default_details(self):
        """Verify publish handles missing details."""
        self.coordinator.publish("action", "task")

        args, _ = self.mock_r.publish.call_args
        payload = json.loads(args[1])
        self.assertEqual(payload['details'], {})

    def test_set_state(self):
        """Verify set_state calls r.set correctly."""
        self.coordinator.set_state("my-key", "my-value", ex=3600)
        self.mock_r.set.assert_called_once_with("my-key", "my-value", ex=3600)

    def test_get_state(self):
        """Verify get_state calls r.get and returns the value."""
        self.mock_r.get.return_value = "cached-value"
        result = self.coordinator.get_state("my-key")
        self.mock_r.get.assert_called_once_with("my-key")
        self.assertEqual(result, "cached-value")

    def test_listen_starts_thread(self):
        """Verify listen starts a background thread."""
        # Use an infinite generator to keep the thread alive
        def infinite_listen():
            while True:
                yield {'type': 'subscribe', 'channel': 'test-channel', 'data': 1}
                time.sleep(0.1)

        self.mock_pubsub.listen.return_value = infinite_listen()

        self.coordinator.listen(lambda x: None)

        self.assertTrue(self.coordinator.running)
        self.assertIsNotNone(self.coordinator.listener_thread)

        # Give it a tiny bit of time to start
        time.sleep(0.1)
        self.assertTrue(self.coordinator.listener_thread.is_alive())

        self.coordinator.stop()

    def test_stop(self):
        """Verify stop sets running to False and joins thread."""
        self.mock_pubsub.listen.return_value = []
        self.coordinator.listen(lambda x: None)

        thread = self.coordinator.listener_thread
        self.coordinator.stop()

        self.assertFalse(self.coordinator.running)
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

if __name__ == "__main__":
    unittest.main()
