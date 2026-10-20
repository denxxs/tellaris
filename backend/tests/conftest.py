import os
import sys
import tempfile
from pathlib import Path

# Isolate tests from the real database and settings.
_tmp = tempfile.mkdtemp(prefix="oracle-test-")
os.environ["ORACLE_VAR_DIR"] = _tmp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
