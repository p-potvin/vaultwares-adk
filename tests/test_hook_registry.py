import unittest
from unittest.mock import MagicMock
from hook_registry import HookRegistry, hooks

class TestHookRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = HookRegistry()

    def test_register(self):
        mock_func = MagicMock()
        self.registry.register("test_event", mock_func)
        self.assertIn("test_event", self.registry._hooks)
        self.assertIn(mock_func, self.registry._hooks["test_event"])

    def test_unregister(self):
        mock_func = MagicMock()
        self.registry.register("test_event", mock_func)
        self.registry.unregister("test_event", mock_func)
        self.assertNotIn(mock_func, self.registry._hooks["test_event"])

    def test_unregister_non_existent_event(self):
        mock_func = MagicMock()
        # Should not raise exception
        self.registry.unregister("non_existent", mock_func)

    def test_unregister_non_existent_hook(self):
        mock_func = MagicMock()
        other_func = MagicMock()
        self.registry.register("test_event", mock_func)
        # Should not raise exception
        self.registry.unregister("test_event", other_func)
        self.assertIn(mock_func, self.registry._hooks["test_event"])

    def test_trigger_single_hook(self):
        mock_func = MagicMock()
        self.registry.register("test_event", mock_func)
        self.registry.trigger("test_event", "arg1", key="value")
        mock_func.assert_called_once_with("arg1", key="value")

    def test_trigger_multiple_hooks(self):
        mock_func1 = MagicMock()
        mock_func2 = MagicMock()
        self.registry.register("test_event", mock_func1)
        self.registry.register("test_event", mock_func2)
        self.registry.trigger("test_event")
        mock_func1.assert_called_once()
        mock_func2.assert_called_once()

    def test_trigger_error_handling(self):
        mock_func1 = MagicMock(side_effect=Exception("Hook error"))
        mock_func2 = MagicMock()
        self.registry.register("test_event", mock_func1)
        self.registry.register("test_event", mock_func2)

        # Should not raise exception when a hook fails
        self.registry.trigger("test_event")

        mock_func1.assert_called_once()
        mock_func2.assert_called_once()

    def test_trigger_no_hooks(self):
        # Should not raise exception
        self.registry.trigger("non_existent")

    def test_global_hooks_instance(self):
        self.assertIsInstance(hooks, HookRegistry)

if __name__ == "__main__":
    unittest.main()
