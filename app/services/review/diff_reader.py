from __future__ import annotations

import re

from app.models.contracts import DiffFileChange, DiffHunk


DIFF_HEADER_PATTERN = re.compile(r"^diff --git a/(?P<left>.+?) b/(?P<right>.+?)$")
HUNK_HEADER_PATTERN = re.compile(r"^@@ .+ @@")


class DiffReader:
    def parse(self, patch_text: str) -> list[DiffFileChange]:
        files: list[DiffFileChange] = []
        current_file_path: str | None = None
        current_change_type = "modified"
        additions = 0
        deletions = 0
        hunks: list[DiffHunk] = []
        current_hunk_header: str | None = None
        current_hunk_lines: list[str] = []

        def flush_hunk() -> None:
            nonlocal current_hunk_header, current_hunk_lines
            if current_hunk_header is None:
                return
            snippet = "\n".join(current_hunk_lines[:12]).strip()
            if snippet:
                hunks.append(
                    DiffHunk(
                        header=current_hunk_header,
                        snippet=snippet,
                    )
                )
            current_hunk_header = None
            current_hunk_lines = []

        def flush_file() -> None:
            nonlocal current_file_path, current_change_type, additions, deletions, hunks
            flush_hunk()
            if current_file_path is None:
                return
            files.append(
                DiffFileChange(
                    file_path=current_file_path,
                    change_type=current_change_type,
                    additions=additions,
                    deletions=deletions,
                    hunks=hunks,
                )
            )
            current_file_path = None
            current_change_type = "modified"
            additions = 0
            deletions = 0
            hunks = []

        for line in patch_text.splitlines():
            diff_header_match = DIFF_HEADER_PATTERN.match(line)
            if diff_header_match is not None:
                flush_file()
                current_file_path = diff_header_match.group("right")
                continue

            if current_file_path is None:
                continue

            if line.startswith("new file mode"):
                current_change_type = "added"
                continue
            if line.startswith("deleted file mode"):
                current_change_type = "deleted"
                continue
            if line.startswith("rename to "):
                current_change_type = "renamed"
                current_file_path = line.removeprefix("rename to ").strip() or current_file_path
                continue
            if line.startswith("+++ b/"):
                current_file_path = line.removeprefix("+++ b/").strip() or current_file_path
                continue

            if HUNK_HEADER_PATTERN.match(line):
                flush_hunk()
                current_hunk_header = line.strip()
                current_hunk_lines = []
                continue

            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

            if current_hunk_header is not None:
                current_hunk_lines.append(line)

        flush_file()
        return files

    def summarize_patch(self, files: list[DiffFileChange]) -> str:
        if not files:
            return "No changed files were detected."

        total_additions = sum(file.additions for file in files)
        total_deletions = sum(file.deletions for file in files)
        lines = [
            f"changed_files: {len(files)}",
            f"total_additions: {total_additions}",
            f"total_deletions: {total_deletions}",
            "files:",
        ]
        for file in files[:8]:
            lines.append(
                f"- {file.file_path} | type={file.change_type} | +{file.additions} -{file.deletions} | hunks={len(file.hunks)}"
            )
        return "\n".join(lines)
