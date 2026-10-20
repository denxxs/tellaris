"""B2B results must not move when other lenses or features are added.

golden_b2b.json was recorded from the B2B path before the lenses work. If a change is
meant to alter B2B results, re-record it deliberately with tests/golden_capture.py.
"""

import json
from pathlib import Path

from tests.golden_capture import run


def test_b2b_results_unchanged():
    expected = json.loads(Path(__file__).with_name("golden_b2b.json").read_text())
    assert run() == expected
