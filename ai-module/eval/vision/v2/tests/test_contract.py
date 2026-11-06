from __future__ import annotations

import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import contract as c


def test_v21_contract_has_exact_interview_quotas():
    assert c.PROTOCOL_VERSION == "v2.1"
    assert c.TOTAL_ITEMS == 160
    assert c.POSITIVES == 80
    assert c.NEGATIVES == 80
    assert c.TEST_ITEMS == 80
    assert c.TEST_POSITIVES == 40
    assert c.TEST_NEGATIVES == 40
    assert c.PER_MAJOR == 10
    assert c.TEST_PER_MAJOR == 5
    assert c.PER_CONFUSER_GROUP == 10
    assert c.TEST_PER_CONFUSER_GROUP == 5
    assert len(c.MAJOR_CODES) == 8
    assert "ai_direct" not in c.ALLOWED_LABEL_SOURCES
