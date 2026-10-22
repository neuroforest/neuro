"""
Unit tests of the module neuro.core.file.blob
"""

import pytest

pytestmark = pytest.mark.unit

NID = "7f1c3e4a-9b2d-4c6e-8a1f-0d2b3c4e5f60"
SUBJECT = "0a9b8c7d-6e5f-4a3b-9c2d-1e0f9a8b7c6d"


class TestBlobKey:
    def test_blob_key(self):
        from neuro.core.file.blob import blob_key
        assert blob_key("image", NID) == f"image/{NID}"
        assert blob_key("media/image/", NID) == f"media/image/{NID}"
        key = blob_key("reads", None, leaf_kind="member", subject_nid=SUBJECT, member="R1.fastq.gz")
        assert key == f"reads/{SUBJECT}/R1.fastq.gz"

    def test_blob_key_rejects(self):
        from neuro.core.file.blob import blob_key
        with pytest.raises(ValueError):
            blob_key("image", None)
        with pytest.raises(ValueError):
            blob_key("reads", NID, leaf_kind="member", subject_nid=SUBJECT)
        with pytest.raises(ValueError):
            blob_key("thumb", NID, leaf_kind="file")

    def test_implicit_nid(self):
        from neuro.core.file.blob import implicit_nid
        assert implicit_nid(f"image/{NID}", "image") == NID
        assert implicit_nid(f"image/{NID}.jpg", "image") is None
        assert implicit_nid(f"image/{SUBJECT}/{NID}", "image") is None
        assert implicit_nid(f"video/{NID}", "image") is None
        assert implicit_nid("image/legacy", "image") is None
        assert implicit_nid(f"image/{NID.upper()}", "image") is None


class TestExtensions:
    def test_extension_for(self):
        from neuro.core.file.blob import extension_for
        assert extension_for("image/jpeg") == "jpg"
        assert extension_for("image/jpeg; charset=binary") == "jpg"
        assert extension_for("IMAGE/PNG") == "png"
        assert extension_for("application/x-unknown") is None
        assert extension_for(None) is None

    def test_canonical_extension(self):
        from neuro.core.file.blob import canonical_extension
        assert canonical_extension(".JPEG") == "jpg"
        assert canonical_extension("thm") == "jpg"
        assert canonical_extension("lrv") == "mp4"
        assert canonical_extension("igc") == "igc"
        assert canonical_extension("") is None


class TestSha256:
    def test_is_sha256(self):
        from neuro.core.file.blob import is_sha256
        assert is_sha256("a" * 64)
        assert not is_sha256("A" * 64)
        assert not is_sha256("a" * 63)
        assert not is_sha256(None)

    def test_sha256_of(self, tmp_path):
        from neuro.core.file.blob import sha256_of
        empty = tmp_path / "empty"
        empty.write_bytes(b"")
        assert sha256_of(empty) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        abc = tmp_path / "abc"
        abc.write_bytes(b"abc")
        assert sha256_of(abc) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
