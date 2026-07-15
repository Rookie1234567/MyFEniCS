from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from benchmarks.task032_final_gates import _canonical_text_sha256


class Task032RecordHashPortabilityTests(unittest.TestCase):
    def test_lf_and_crlf_checkouts_have_the_same_evidence_hash(self) -> None:
        lf_payload = b'{\n  "value": 1\n}\n'
        crlf_payload = lf_payload.replace(b"\n", b"\r\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lf_path = root / "lf.json"
            crlf_path = root / "crlf.json"
            lf_path.write_bytes(lf_payload)
            crlf_path.write_bytes(crlf_payload)

            expected = hashlib.sha256(lf_payload).hexdigest()
            self.assertEqual(_canonical_text_sha256(lf_path), expected)
            self.assertEqual(_canonical_text_sha256(crlf_path), expected)

    def test_non_line_ending_change_still_invalidates_the_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            first.write_text('{"value": 1}\n', encoding="utf-8", newline="\n")
            second.write_text('{"value": 2}\n', encoding="utf-8", newline="\n")

            self.assertNotEqual(
                _canonical_text_sha256(first),
                _canonical_text_sha256(second),
            )


if __name__ == "__main__":
    unittest.main()
