"""Missing downloaded outputs and checkbox selection, shared by both settings UIs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

from blackboard_sync.config import Config
from blackboard_sync.state import State
from blackboard_sync.sync import run_lock
from blackboard_sync.system import sync_root

T_TAB = "Silinenler"
T_EMPTY = "Silinmiş dosya yok."
T_HINT = ("Kaydedilmiş klasörden silinen dosyaları seçerek geri getirebilirsiniz. "
          "Listeden kaldırılan dosyalar tekrar önerilmez.")
T_SELECT_ALL = "Tümünü seç"
T_DOWNLOAD = "Seçilenleri indir"
T_DISMISS = "Listeden kaldır"


@dataclass(frozen=True)
class MissingOutput:
    key: str
    path: str
    term: str
    course: str
    name: str
    folder: str


def missing_outputs(state: State, root: Path) -> list[MissingOutput]:
    """Only safe relative paths inside this University folder, never dismissed entries."""
    result = []
    resolved = root.resolve()
    for key, output in state.outputs.items():
        rel = PurePosixPath(output["path"])
        if output.get("dismissed") or rel.is_absolute() or ".." in rel.parts:
            continue
        target = root / rel
        try:
            target.resolve().relative_to(resolved)
        except ValueError:
            continue
        if target.exists():
            continue
        parts = rel.parts
        result.append(MissingOutput(key, str(rel), parts[0] if len(parts) > 2 else "Diğer",
                                    parts[1] if len(parts) > 2 else "Diğer", rel.name, str(rel.parent)))
    return sorted(result, key=lambda row: (row.term.casefold(), row.course.casefold(), row.path.casefold(), row.key))


def load_missing(config: Config, dest: Path) -> list[MissingOutput]:
    """The missing files of the chosen folder ``dest`` (they belong in its University folder)."""
    return missing_outputs(State.load(config.state_file, backup=False), sync_root(dest))


def dismiss_missing(config: Config, dest: Path, keys: Iterable[str]) -> None:
    """Serialize state edits with CLI jobs; don't lose a sync's newly saved outputs."""
    config.ensure_data_dir()
    with run_lock(config.lock_file):
        state = State.load(config.state_file, backup=False)
        eligible = {row.key for row in missing_outputs(state, sync_root(dest))}
        state.dismiss_outputs(set(keys) & eligible)
        state.save()


@dataclass
class DeletedSelection:
    rows: list[MissingOutput] = field(default_factory=list)
    selected: set[str] = field(default_factory=set)

    def refresh(self, rows: list[MissingOutput]) -> None:
        self.rows = rows
        self.selected.intersection_update(row.key for row in rows)

    def select(self, key: str, checked: bool) -> None:
        if checked and any(row.key == key for row in self.rows):
            self.selected.add(key)
        else:
            self.selected.discard(key)

    def select_all(self) -> None:
        self.selected = {row.key for row in self.rows}

    def keys(self) -> list[str]:
        return [row.key for row in self.rows if row.key in self.selected]
