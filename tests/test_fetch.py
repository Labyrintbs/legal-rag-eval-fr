import hashlib

import pytest

from legalrag.fetch import ChecksumError, RawFile, fetch_file, sha256_of


def make_source(tmp_path, content=b"raw data"):
    src = tmp_path / "src" / "file.bin"
    src.parent.mkdir()
    src.write_bytes(content)
    return src, RawFile("file.bin", src.as_uri(), hashlib.sha256(content).hexdigest())


def test_downloads_then_skips_when_checksum_matches(tmp_path):
    src, raw = make_source(tmp_path)
    dest = tmp_path / "raw"
    assert fetch_file(raw, dest) == "downloaded"
    assert sha256_of(dest / "file.bin") == raw.sha256
    src.unlink()  # a second call must not need the network
    assert fetch_file(raw, dest) == "present"


def test_checksum_mismatch_raises_and_keeps_file_for_inspection(tmp_path):
    _, raw = make_source(tmp_path)
    bad = RawFile(raw.name, raw.url, "0" * 64)
    dest = tmp_path / "raw"
    with pytest.raises(ChecksumError):
        fetch_file(bad, dest)
    assert not (dest / "file.bin").exists()
    assert (dest / "file.bin.mismatch").exists()


def test_wrong_existing_file_is_replaced_only_by_a_correct_download(tmp_path):
    _, raw = make_source(tmp_path)
    dest = tmp_path / "raw"
    dest.mkdir()
    (dest / "file.bin").write_bytes(b"corrupted")
    assert fetch_file(raw, dest) == "downloaded"
    assert sha256_of(dest / "file.bin") == raw.sha256
