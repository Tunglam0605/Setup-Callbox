import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.callbox_flasher.src.self_update import (
    GitHubReleaseUpdater,
    SemVer,
    UpdateError,
    apply_verified_update,
)


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, content_length=None):
        super().__init__(data)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class FakeOpener:
    def __init__(self, mapping):
        self.mapping = mapping

    def __call__(self, request, timeout=0):
        data = self.mapping[request.full_url]
        return FakeResponse(data, len(data))


def release_payload(version: str, exe_bytes: bytes):
    tag = "v" + version
    base = f"https://github.com/Tunglam0605/Setup-Callbox/releases/download/{tag}"
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "html_url": f"https://github.com/Tunglam0605/Setup-Callbox/releases/tag/{tag}",
        "body": "notes",
        "assets": [
            {
                "name": "Setup-CallBox.exe",
                "browser_download_url": base + "/Setup-CallBox.exe",
                "size": len(exe_bytes),
            },
            {
                "name": "Setup-CallBox.exe.sha256",
                "browser_download_url": base + "/Setup-CallBox.exe.sha256",
                "size": 90,
            },
        ],
    }


class SelfUpdateTests(unittest.TestCase):
    def test_semver_orders_versions(self):
        self.assertLess(SemVer.parse("1.0.9"), SemVer.parse("1.1.0"))

    def test_check_detects_new_release(self):
        exe = b"new-exe"
        payload = release_payload("1.1.0", exe)
        api = "https://api.github.com/repos/Tunglam0605/Setup-Callbox/releases/latest"
        updater = GitHubReleaseUpdater(opener=FakeOpener({api: json.dumps(payload).encode()}))
        result = updater.check("1.0.0")
        self.assertTrue(result.available)
        self.assertEqual(str(result.release.version), "1.1.0")

    def test_check_reports_current_release(self):
        exe = b"same"
        payload = release_payload("1.0.0", exe)
        api = "https://api.github.com/repos/Tunglam0605/Setup-Callbox/releases/latest"
        updater = GitHubReleaseUpdater(opener=FakeOpener({api: json.dumps(payload).encode()}))
        self.assertFalse(updater.check("1.0.0").available)

    def test_check_rejects_wrong_asset_url(self):
        exe = b"x"
        payload = release_payload("1.1.0", exe)
        payload["assets"][0]["browser_download_url"] = "https://evil.example/Setup-CallBox.exe"
        api = "https://api.github.com/repos/Tunglam0605/Setup-Callbox/releases/latest"
        updater = GitHubReleaseUpdater(opener=FakeOpener({api: json.dumps(payload).encode()}))
        with self.assertRaises(UpdateError):
            updater.check("1.0.0")

    def test_download_verifies_sha256(self):
        exe = b"verified-new-exe"
        payload = release_payload("1.1.0", exe)
        api = "https://api.github.com/repos/Tunglam0605/Setup-Callbox/releases/latest"
        exe_url = payload["assets"][0]["browser_download_url"]
        hash_url = payload["assets"][1]["browser_download_url"]
        sha = hashlib.sha256(exe).hexdigest()
        opener = FakeOpener({
            api: json.dumps(payload).encode(),
            exe_url: exe,
            hash_url: f"{sha}  Setup-CallBox.exe\n".encode(),
        })
        updater = GitHubReleaseUpdater(opener=opener)
        release = updater.check("1.0.0").release
        with tempfile.TemporaryDirectory() as temp:
            old = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = temp
            try:
                path, actual = updater.download(release)
            finally:
                if old is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = old
            self.assertEqual(path.read_bytes(), exe)
            self.assertEqual(actual, sha)

    def test_download_rejects_bad_hash(self):
        exe = b"verified-new-exe"
        payload = release_payload("1.1.0", exe)
        api = "https://api.github.com/repos/Tunglam0605/Setup-Callbox/releases/latest"
        exe_url = payload["assets"][0]["browser_download_url"]
        hash_url = payload["assets"][1]["browser_download_url"]
        opener = FakeOpener({
            api: json.dumps(payload).encode(),
            exe_url: exe,
            hash_url: (("0" * 64) + "  Setup-CallBox.exe\n").encode(),
        })
        updater = GitHubReleaseUpdater(opener=opener)
        release = updater.check("1.0.0").release
        with tempfile.TemporaryDirectory() as temp:
            old = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = temp
            try:
                with self.assertRaises(UpdateError):
                    updater.download(release)
            finally:
                if old is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = old

    def test_apply_verified_update_replaces_target_without_relaunch(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "new.exe"
            target = base / "Setup-CallBox.exe"
            source.write_bytes(b"new-version")
            target.write_bytes(b"old-version")
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            apply_verified_update(source, target, 0, sha, relaunch=False)
            self.assertEqual(target.read_bytes(), b"new-version")
            self.assertFalse((base / "Setup-CallBox.exe.update-backup").exists())

    def test_apply_verified_update_rejects_wrong_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "new.exe"
            target = base / "Setup-CallBox.exe"
            source.write_bytes(b"new-version")
            target.write_bytes(b"old-version")
            with self.assertRaises(UpdateError):
                apply_verified_update(source, target, 0, "0" * 64, relaunch=False)
            self.assertEqual(target.read_bytes(), b"old-version")


if __name__ == "__main__":
    unittest.main()
