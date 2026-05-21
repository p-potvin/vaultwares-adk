
import unittest
from unittest.mock import patch
from pathlib import Path
import os
import sys

# Add tools to path so we can import audit_agent_surfaces
sys.path.append(os.path.join(os.getcwd(), "tools"))
import audit_agent_surfaces

class TestRootDiscovery(unittest.TestCase):

    @patch("os.getenv")
    @patch("audit_agent_surfaces.parse_args")
    def test_default_cwd(self, mock_parse_args, mock_getenv):
        # Setup: No CLI args, no env var
        mock_parse_args.return_value.roots = []
        mock_getenv.return_value = None

        # We need to mock main's dependencies to avoid full execution
        with patch("audit_agent_surfaces.discover_repos") as mock_discover:
            mock_discover.return_value = []
            with patch("audit_agent_surfaces.Path.write_text"):
                with patch("builtins.print"):
                    audit_agent_surfaces.main([])

            # Verify roots used in discover_repos
            # First call, first argument
            called_roots = mock_discover.call_args[0][0]
            self.assertEqual(called_roots, [Path.cwd()])

    @patch("os.getenv")
    @patch("audit_agent_surfaces.parse_args")
    def test_env_var(self, mock_parse_args, mock_getenv):
        # Setup: No CLI args, env var set
        mock_parse_args.return_value.roots = []
        mock_getenv.return_value = "/tmp/repo1, /tmp/repo2"

        with patch("audit_agent_surfaces.discover_repos") as mock_discover:
            mock_discover.return_value = []
            with patch("audit_agent_surfaces.Path.write_text"):
                with patch("builtins.print"):
                    audit_agent_surfaces.main([])

            called_roots = mock_discover.call_args[0][0]
            self.assertEqual(called_roots, [Path("/tmp/repo1"), Path("/tmp/repo2")])

    @patch("os.getenv")
    @patch("audit_agent_surfaces.parse_args")
    def test_cli_args_override_all(self, mock_parse_args, mock_getenv):
        # Setup: CLI args set, env var also set
        mock_parse_args.return_value.roots = ["/cli/repo"]
        mock_getenv.return_value = "/env/repo"

        with patch("audit_agent_surfaces.discover_repos") as mock_discover:
            mock_discover.return_value = []
            with patch("audit_agent_surfaces.Path.write_text"):
                with patch("builtins.print"):
                    audit_agent_surfaces.main(["--roots", "/cli/repo"])

            called_roots = mock_discover.call_args[0][0]
            self.assertEqual(called_roots, [Path("/cli/repo")])

if __name__ == "__main__":
    unittest.main()
