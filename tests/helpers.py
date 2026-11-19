from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / ".test_tmp"


@contextmanager
def workspace_tempdir():
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    yield str(path)
