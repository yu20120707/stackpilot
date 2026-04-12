from app.services.review.diff_reader import DiffReader


PATCH_TEXT = """diff --git a/app/services/tickets.py b/app/services/tickets.py
index 0000000..1111111 100644
--- a/app/services/tickets.py
+++ b/app/services/tickets.py
@@ -10,2 +10,4 @@ def build_ticket(payload):
-title = payload["title"]
+title = payload.get("title").strip()
+owner = payload.get("owner", "unknown")
 return {"title": title, "owner": owner}
"""


def test_diff_reader_parses_changed_files_and_hunks() -> None:
    reader = DiffReader()

    files = reader.parse(PATCH_TEXT)

    assert len(files) == 1
    assert files[0].file_path == "app/services/tickets.py"
    assert files[0].additions == 2
    assert files[0].deletions == 1
    assert files[0].hunks[0].header == "@@ -10,2 +10,4 @@ def build_ticket(payload):"
