import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Direct test suite to an isolated test SQLite database so production/local tektutors.db remains pristine
TEST_DB_PATH = ROOT_DIR / "test_tektutors.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["APP_ENV"] = "testing"
os.environ["DEBUG"] = "False"
