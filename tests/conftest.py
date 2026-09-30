import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finanze_app.service import FinanceService


@pytest.fixture
def service(tmp_path):
    instance = FinanceService(tmp_path / "finanze.xlsx")
    instance.snapshot()
    return instance
