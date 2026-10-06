from io import BytesIO
import tarfile

import pytest

from app.services.repository_archive import _extract_source_archive
from app.services.repository_intelligence import GitHubUnavailable


def make_archive(entries: list[tuple[str, bytes, bytes | None]]) -> bytes:
    archive = BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        for name, content, linkname in entries:
            member = tarfile.TarInfo(name)
            member.mode = 0o644
            if linkname is not None:
                member.type = tarfile.SYMTYPE
                member.linkname = linkname.decode()
                tar.addfile(member)
            else:
                member.size = len(content)
                tar.addfile(member, BytesIO(content))
    return archive.getvalue()


def test_source_archive_extracts_regular_files_and_skips_symlinks(tmp_path):
    archive = make_archive(
        [
            ("repo-main/src/main.py", b"print('safe')\n", None),
            ("repo-main/link.py", b"", b"../../outside.py"),
        ]
    )

    _extract_source_archive(archive, tmp_path)

    assert (tmp_path / "src" / "main.py").read_text() == "print('safe')\n"
    assert not (tmp_path / "link.py").exists()


def test_source_archive_rejects_parent_path_traversal(tmp_path):
    archive = make_archive([("repo-main/../../outside.txt", b"no", None)])

    with pytest.raises(GitHubUnavailable, match="unsafe path"):
        _extract_source_archive(archive, tmp_path)
