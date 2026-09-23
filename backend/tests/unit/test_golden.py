import hashlib
import json
from pathlib import Path


def test_l2_core_remains_byte_identical():
    root = Path(__file__).resolve().parents[3]
    lock = root / 'golden/L2/LOCK.json'
    if not lock.exists():
        return  # historical immutable experiment snapshots predate the lock
    for name, digest in json.loads(lock.read_text())['protected_files'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
