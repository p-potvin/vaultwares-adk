import unittest
import os
from omx_integration.utils.team_utils import is_safe_path, safe_write_file

class TestTeamUtilsSafety(unittest.TestCase):
    def test_is_safe_path(self):
        base = "/app/project"
        self.assertTrue(is_safe_path("/app/project/file.txt", base))
        self.assertTrue(is_safe_path("/app/project/dir/file.txt", base))
        self.assertFalse(is_safe_path("/app/project/../other.txt", base))
        self.assertFalse(is_safe_path("/etc/passwd", base))
        # Partial match protection
        self.assertFalse(is_safe_path("/app/project-secret/file.txt", base))

    def test_safe_write_file_traversal(self):
        # Using current directory as base
        self.assertFalse(safe_write_file("../traversal.txt", "content"))
        self.assertTrue(safe_write_file("safe.txt", "content"))
        if os.path.exists("safe.txt"):
            os.remove("safe.txt")

if __name__ == "__main__":
    unittest.main()
