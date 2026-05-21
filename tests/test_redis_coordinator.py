import unittest
from unittest.mock import MagicMock, patch
import json
import sys
from types import ModuleType

# Mock redis module before importing RedisCoordinator
mock_redis_module = ModuleType('redis')
mock_redis_module.Redis = MagicMock()
sys.modules['redis'] = mock_redis_module

import time
from redis_coordinator import RedisCoordinator

class TestRedisCoordinator(unittest.TestCase):
    def setUp(self):
        self.agent_id = "test_agent"
        self.channel = "test_channel"
        # Reset the mock for each test
        mock_redis_module.Redis.reset_mock()
        self.coordinator = RedisCoordinator(self.agent_id, channel=self.channel)
        self.mock_r = self.coordinator.r

    def test_init(self):
        self.assertEqual(self.coordinator.agent_id, self.agent_id)
        self.assertEqual(self.coordinator.channel, self.channel)
        self.mock_r.pubsub.assert_called_once()

    def test_publish(self):
        action = "test_action"
        task = "test_task"
        details = {"key": "value"}
        self.coordinator.publish(action, task, details)

        expected_msg = {
            'agent': self.agent_id,
            'action': action,
            'task': task,
            'details': details
        }
        self.mock_r.publish.assert_called_once_with(self.channel, json.dumps(expected_msg))

    def test_set_state(self):
        self.coordinator.set_state("key", "value", ex=10)
        self.mock_r.set.assert_called_once_with("key", "value", ex=10)

    def test_get_state(self):
        self.mock_r.get.return_value = "value"
        result = self.coordinator.get_state("key")
        self.assertEqual(result, "value")
        self.mock_r.get.assert_called_once_with("key")

    def test_listen_and_stop(self):
        mock_callback = MagicMock()

        # Mock pubsub.listen() to return one valid message and then block
        def mock_listen():
            yield {'type': 'message', 'data': json.dumps({'hello': 'world'})}
            while self.coordinator.running:
                time.sleep(0.1)

        self.coordinator.pubsub.listen = mock_listen

        self.coordinator.listen(mock_callback)

        # Give it a moment to process
        time.sleep(0.2)

        mock_callback.assert_called_once_with({'hello': 'world'})
        self.assertTrue(self.coordinator.running)

        self.coordinator.stop()
        self.assertFalse(self.coordinator.running)
        if self.coordinator.listener_thread:
            self.coordinator.listener_thread.join(timeout=1)
            self.assertFalse(self.coordinator.listener_thread.is_alive())

    def test_listen_malformed_json(self):
        mock_callback = MagicMock()

        def mock_listen():
            yield {'type': 'message', 'data': 'not a json'}
            while self.coordinator.running:
                time.sleep(0.1)

        self.coordinator.pubsub.listen = mock_listen

        with self.assertLogs('redis_coordinator', level='WARNING') as cm:
            self.coordinator.listen(mock_callback)
            time.sleep(0.2)
            self.coordinator.stop()

        mock_callback.assert_not_called()
        self.assertTrue(any("Skipping malformed Redis message" in output for output in cm.output))

if __name__ == '__main__':
    unittest.main()
