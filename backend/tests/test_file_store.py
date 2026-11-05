from app.ingest.file_store import hash_file, store_file


def test_hash_file_is_deterministic(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello world")
    assert hash_file(f) == hash_file(f)


def test_hash_file_differs_for_different_content(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("hello")
    b = tmp_path / "b.txt"
    b.write_text("goodbye")
    assert hash_file(a) != hash_file(b)


def test_store_file_is_content_addressed(tmp_path):
    files_dir = tmp_path / "files"
    source = tmp_path / "original.txt"
    source.write_text("some content")

    sha256, stored_path = store_file(source, files_dir)

    assert stored_path == files_dir / f"{sha256}.txt"
    assert stored_path.exists()
    assert stored_path.read_text() == "some content"


def test_store_file_skips_copy_if_already_present(tmp_path):
    files_dir = tmp_path / "files"
    source = tmp_path / "original.txt"
    source.write_text("some content")

    sha256_a, path_a = store_file(source, files_dir)
    mtime_a = path_a.stat().st_mtime_ns

    sha256_b, path_b = store_file(source, files_dir)

    assert sha256_a == sha256_b
    assert path_a == path_b
    assert path_b.stat().st_mtime_ns == mtime_a
