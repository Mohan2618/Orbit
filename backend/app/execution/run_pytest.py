"""Run pytest after importing it without exposing the source as import priority."""

import sys

sys.path.insert(0, "/tmp/orbit-packages")
import pytest  # noqa: E402 - the trusted dependency path must precede source imports

sys.path.append("/workspace")
raise SystemExit(pytest.main(["-q", "/workspace", *sys.argv[1:]]))
