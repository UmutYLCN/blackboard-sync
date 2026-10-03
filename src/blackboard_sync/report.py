"""What a sync run found, in human and machine-readable form."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


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
    warnings: list[str] = field(default_factory=list)

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
        )

    def summary_line(self) -> str:
        """e.g. "CSE303: 2 new files, 1 new announcement"."""
        parts = []
        for count, singular in (
            (len(self.new_files), "new file"),
            (len(self.updated_files), "updated file"),
            (len(self.new_notes), "new note"),
            (len(self.updated_notes), "updated note"),
            (len(self.new_announcements), "new announcement"),
            (len(self.updated_announcements), "updated announcement"),
        ):
            if count:
                parts.append(f"{count} {singular}{'' if count == 1 else 's'}")
        return f"{self.code}: {', '.join(parts) if parts else 'no changes'}"


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

    def totals(self) -> dict[str, int]:
        keys = (
            "new_files",
            "updated_files",
            "new_notes",
            "updated_notes",
            "new_announcements",
            "updated_announcements",
        )
        return {k: sum(len(getattr(c, k)) for c in self.courses) for k in keys}

    def to_dict(self) -> dict:
        data = asdict(self)
        data["totals"] = self.totals()
        data["changed_courses"] = [
            {"code": c.code, "name": c.name, "summary": c.summary_line(), "changes": c.change_count}
            for c in self.courses
            if c.change_count
        ]
        return data

    def render_text(self) -> str:
        if self.status != "ok":
            return self.message
        verb = "Would sync" if self.dry_run else "Synced"
        lines = [f"{verb} {len(self.courses)} course(s) for {', '.join(self.terms) or 'no term'} into {self.dest}"]
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
        lines.append("Nothing new." if not changed else f"{changed} course(s) had changes.")
        return "\n".join(lines)
