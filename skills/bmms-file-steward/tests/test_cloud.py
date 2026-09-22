"""纯离线合成样本；不调用真实网盘、不接触用户文件。"""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cloud_verify.py"
SPEC = importlib.util.spec_from_file_location("cloud_verify", SCRIPT)
CLOUD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLOUD)


class CloudEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.payload = b"complete candidate bytes\x00\xff"
        self.manifest = {
            "schema_version": 1, "task_id": "synthetic-task", "provider": "synthetic-provider",
            "scope": "/Documents excluding /Backups", "entries": []}
        for name in ["a", "b"]:
            (self.cache / name).write_bytes(self.payload)
            self.manifest["entries"].append({
                "candidate_group": "group-one", "remote_id": "remote-" + name,
                "remote_path": "/Documents/" + name, "size": len(self.payload),
                "revision": "v1", "cache_path": name,
                "fingerprint": {"semantics": "opaque", "value": "not-a-standard-md5"}})

    def test_equal_complete_bytes_are_evidence_not_move_authorization(self):
        result = CLOUD.verify(self.manifest, self.cache)
        self.assertTrue(result["groups"][0]["cached_content_equal"])
        self.assertFalse(result["groups"][0]["move_authorized"])
        self.assertTrue(result["groups"][0]["purpose_review_required"])
        self.assertFalse(result["live_download_verified"])
        self.assertFalse(result["live_move_verified"])
        self.assertEqual(result["entries"][0]["bytes_read"], len(self.payload))

    def test_same_opaque_fingerprint_different_bytes_are_not_equal(self):
        (self.cache / "b").write_bytes(b"x" * len(self.payload))
        result = CLOUD.verify(self.manifest, self.cache)
        self.assertFalse(result["groups"][0]["cached_content_equal"])

    def test_different_upstream_fingerprints_do_not_override_equal_bytes(self):
        self.manifest["entries"][1]["fingerprint"]["value"] = "different-provider-value"
        self.assertTrue(CLOUD.verify(self.manifest, self.cache)["groups"][0]["cached_content_equal"])

    def test_truncation_is_rejected(self):
        (self.cache / "b").write_bytes(self.payload[:-1])
        with self.assertRaises(CLOUD.VerificationError):
            CLOUD.verify(self.manifest, self.cache)

    def test_missing_file_is_rejected(self):
        (self.cache / "b").unlink()
        with self.assertRaises(OSError):
            CLOUD.verify(self.manifest, self.cache)

    def test_duplicate_id_and_cache_alias_are_rejected(self):
        for key in ["remote_id", "cache_path"]:
            with self.subTest(key=key):
                manifest = copy.deepcopy(self.manifest)
                manifest["entries"][1][key] = manifest["entries"][0][key]
                with self.assertRaises(CLOUD.VerificationError):
                    CLOUD.verify(manifest, self.cache)

    def test_external_symlink_and_parent_traversal_rejected(self):
        outside = self.root / "outside"
        outside.write_bytes(self.payload)
        (self.cache / "b").unlink()
        try:
            (self.cache / "b").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("当前环境无法创建软链接")
        with self.assertRaises(CLOUD.VerificationError):
            CLOUD.verify(self.manifest, self.cache)
        self.manifest["entries"][1]["cache_path"] = "../outside"
        with self.assertRaises(CLOUD.VerificationError):
            CLOUD.verify(self.manifest, self.cache)
        self.assertEqual(outside.read_bytes(), self.payload)

    def test_missing_revision_requires_explanation(self):
        self.manifest["entries"][1]["revision"] = None
        with self.assertRaises(CLOUD.VerificationError):
            CLOUD.verify(self.manifest, self.cache)
        self.manifest["entries"][1]["revision_note"] = "Synthetic interface has no revision field."
        self.assertEqual(CLOUD.verify(self.manifest, self.cache)["status"], "verified_cached_bytes")

    def test_cli_json_success_and_rejection(self):
        manifest_path = self.root / "manifest.json"
        manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        command = [sys.executable, str(SCRIPT), str(manifest_path), "--cache-root", str(self.cache)]
        proc = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["verification_level"], "offline_download_copy_only")
        (self.cache / "b").write_bytes(b"truncated")
        proc = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
