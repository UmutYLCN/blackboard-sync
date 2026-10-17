"""What a sync run found, in human and machine-readable form."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from blackboard_sync.i18n import tr


@dataclass
class CourseReport:
    code: str
    name: str
    folder: str
    new_files: list[str] = field(default_factory=list)
    updated_files: list[str] = field(default_factory=list)
    new_notes: list[str] = field(default_factory=list)
    updated_notes: list[str] = field(default_factory=list)
    new_announcements: list[str] = field(default_factory=list)
    updated_announcements: list[str] = field(default_factory=list)
    skipped_large_files: int = 0
    warnings: list[str] = field(default_factory=list)
    content_error: str = ""  # why the course's content could not be read at all

    @property
    def change_count(self) -> int:
        return sum(
            len(getattr(self, name))
            for name in (
                "new_files",
                "updated_files",
                "new_notes",
                "updated_notes",
                "new_announcements",
                "updated_announcements",
            )
        ) + self.skipped_large_files

    def summary_line(self) -> str:
        """e.g. "CSE303: 2 new files, 1 new announcement"."""
        parts = []
        for count, one, many in (
            (len(self.new_files), tr("new file"), tr("new files")),
            (len(self.updated_files), tr("updated file"), tr("updated files")),
            (len(self.new_notes), tr("new note"), tr("new notes")),
            (len(self.updated_notes), tr("updated note"), tr("updated notes")),
            (len(self.new_announcements), tr("new announcement"), tr("new announcements")),
            (len(self.updated_announcements), tr("updated announcement"), tr("updated announcements")),
            (self.skipped_large_files, tr("large file not downloaded"), tr("large files not downloaded")),
        ):
            if count:
                parts.append(f"{count} {one if count == 1 else many}")
        return f"{self.code}: {', '.join(parts) if parts else tr('no changes')}"


@dataclass
class SyncReport:
    status: str = "ok"  # ok | login_required | error | locked
    message: str = ""
    started_at: str = ""
    finished_at: str = ""
    dry_run: bool = False
    dest: str = ""
    terms: list[str] = field(default_factory=list)
    courses: list[CourseReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    past_term: str = ""
    # The one-time move of an older version's files from the chosen folder into
    # the University folder (``relocate.migrate_to_root``), done before syncing.
    moved_into_root: int = 0
    left_outside_root: list[str] = field(default_factory=list)  # relative paths that stayed

    def totals(self) -> dict[str, int]:
        keys = (
            "new_files",
            "updated_files",
            "new_notes",
            "updated_notes",
            "new_announcements",
            "updated_announcements",
            "skipped_large_files",
        )
        return {
            k: sum(getattr(c, k) if k == "skipped_large_files" else len(getattr(c, k)) for c in self.courses)
            for k in keys
        }

    def to_dict(self) -> dict:
        data = asdict(self)
        data["totals"] = self.totals()
        data["changed_courses"] = [
            {"code": c.code, "name": c.name, "summary": c.summary_line(), "changes": c.change_count}
            for c in self.courses
            if c.change_count
        ]
        return data

    def migration_lines(self) -> list[str]:
        if not self.moved_into_root and not self.left_outside_root:
            return []
        lines = [tr("Moved {n} file(s) into {folder}").format(n=self.moved_into_root, folder=self.dest)]
        if self.left_outside_root:
            lines.append(tr("{n} file(s) could not be moved and stayed where they were:").format(
                n=len(self.left_outside_root)))
            lines += [f"  ! {rel}" for rel in self.left_outside_root]
        return lines

    def render_text(self) -> str:
        if self.status != "ok":
            return "\n".join([*self.migration_lines(), self.message])
        line = tr("Would sync {n} course(s) for {terms} into {folder}") if self.dry_run else tr(
            "Synced {n} course(s) for {terms} into {folder}")
        lines = self.migration_lines()
        lines.append(line.format(n=len(self.courses), terms=", ".join(self.terms) or tr("no term"), folder=self.dest))
        if self.past_term:
            lines.append(tr("Past term: downloaded once, not updated automatically."))
        for course in self.courses:
            lines.append(f"  {course.summary_line()}")
            for label, paths in (
                ("+", course.new_files + course.new_notes + course.new_announcements),
                ("~", course.updated_files + course.updated_notes + course.updated_announcements),
            ):
                lines += [f"      {label} {p}" for p in paths]
            lines += [f"      ! {w}" for w in course.warnings]
        lines += [f"  ! {w}" for w in self.warnings]
        changed = sum(1 for c in self.courses if c.change_count)
        lines.append(tr("Nothing new.") if not changed else tr("{n} course(s) had changes.").format(n=changed))
        return "\n".join(lines)
