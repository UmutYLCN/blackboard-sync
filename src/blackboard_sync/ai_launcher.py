"""Open the current term's folder in a terminal and start the AI tool the student chose.

Settings → AI assistant picks the tool (``Settings.ai_cli``: Claude Code, Gemini CLI or Codex)
and whether it continues its last session in that folder (``Settings.ai_resume``). The Home
card and the menu bar / tray item call ``launch``, which answers with a ``LaunchResult``: the
terminal opened, or why not (``Failure``). Everything else here is plain logic, testable
without a GUI or a terminal:

- ``term_folder``: which folder opens (the term most ticked courses are in, never "No term").
- ``detect``: where each tool is installed. A GUI app does not get the shell's ``PATH`` (on
  macOS launchd gives ``/usr/bin:/bin:/usr/sbin:/sbin``), so macOS asks the student's login
  shell and then looks in the usual install folders; Windows searches ``PATH`` with
  ``PATHEXT`` plus the folders the installers use.
- ``macos_script`` / ``windows_script`` and the ``*_commands`` builders: what runs.

The folder name comes from Blackboard (the term's name), so it never reaches a shell as it is:
on macOS every value in the script is quoted with ``shlex.quote`` and the script itself is
passed to ``open`` as one argument; on Windows the script is handed to PowerShell as
``-EncodedCommand`` (base64), so neither ``wt.exe`` nor ``cmd.exe`` parses any of it, and every
value inside is a single-quoted PowerShell string.

Resuming: each tool is started with its "continue the last session here" arguments
(``AiTool.resume``). How the tools behave when the folder has no earlier session was not
verified, so if the resume command fails within ``FALLBACK_SECONDS`` the script says so and
starts a new session. A session that ran and then ended normally does not fall through.
"""

from __future__ import annotations

import base64
import enum
import logging
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Callable, Collection, Mapping

from blackboard_sync.config import Config
from blackboard_sync.i18n import tr
from blackboard_sync.settings import AI_CLAUDE, AI_CLIS, AI_CODEX, AI_GEMINI
from blackboard_sync.system import is_windows, make_private_dir

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiTool:
    key: str  # settings.AI_CLIS; also the program's name
    name: str  # as the vendor writes it
    resume: tuple[str, ...]  # continue the most recent session in the current folder
    install_url: str
    fresh: tuple[str, ...] = ()  # a new session


# Verified 2026-11-26: ``claude --help`` (Claude Code 2.1.332): "-c, --continue  Continue the most
# recent conversation in the current directory". ``codex resume --help`` (codex-cli 0.171.0):
# "--last  Continue the most recent session without showing the picker"; the picker filters by the
# current folder ("--all ... disables cwd filtering"). Gemini CLI v0.71.1,
# packages/cli/src/config/config.ts: "-r, --resume  Resume a previous session. Use "latest" for most
# recent"; its sessions are per project folder.
TOOLS = {tool.key: tool for tool in (
    AiTool(AI_CLAUDE, "Claude Code", ("--continue",), "https://code.claude.com/docs/en/setup"),
    AiTool(AI_GEMINI, "Gemini CLI", ("--resume", "latest"), "https://github.com/google-gemini/gemini-cli"),
    AiTool(AI_CODEX, "Codex", ("resume", "--last"), "https://github.com/openai/codex"),
)}
assert tuple(TOOLS) == AI_CLIS

# A resume command that fails sooner than this found no session to continue: start a new one.
FALLBACK_SECONDS = 5
T_NO_SESSION = tr("No earlier session here, starting a new one.")


class Failure(enum.Enum):
    """Why ``launch`` opened no terminal."""

    NO_AI = "no_ai"  # Settings → AI assistant says None
    CLI_MISSING = "cli_missing"  # the chosen tool is not installed (``LaunchResult.tool`` names it)
    FOLDER_MISSING = "folder_missing"  # the term folder is not on disk yet (``LaunchResult.folder``)
    TERMINAL_FAILED = "terminal_failed"  # Terminal / Windows Terminal did not start (``LaunchResult.error``)


@dataclass(frozen=True)
class LaunchResult:
    failure: Failure | None = None  # None: the terminal opened
    tool: AiTool | None = None
    folder: Path | None = None  # the term folder, once known
    error: str = ""  # what the terminal reported, for TERMINAL_FAILED

    @property
    def ok(self) -> bool:
        return self.failure is None


# -- which folder ----------------------------------------------------------------------------------

def _is_termless(info: Mapping) -> bool:
    from blackboard_sync.sync import NO_TERM

    folder = info.get("folder")
    first = PurePosixPath(folder).parts[0] if isinstance(folder, str) and folder else ""
    return info.get("termless") is True or info.get("term") == NO_TERM or first == NO_TERM


def _term_age(name: str) -> tuple[int, int]:
    from blackboard_sync.sync import academic_order

    return academic_order(name) or (-1, -1)


def term_folder(root: Path, courses: Mapping[str, object], disabled: Collection[str] = ()) -> Path:
    """The current term's folder inside ``root`` (the University folder).

    ``courses`` is ``State.courses`` (what the last sync found: ``folder`` is "<term>/<course>"),
    ``disabled`` the unticked course ids. The term folder is the one most ticked courses are in;
    on a tie the newer term by its name ("2026-2027 Güz" over "2025-2026 Bahar"). Courses without
    a term never count. Before the first sync (no courses) it is ``root`` itself.
    """
    counts: Counter[str] = Counter()
    for course_id, info in courses.items():
        if course_id in disabled or not isinstance(info, Mapping) or _is_termless(info):
            continue
        folder = info.get("folder")
        if not isinstance(folder, str):
            continue
        parts = PurePosixPath(folder).parts
        if len(parts) < 2 or folder.startswith("/") or ".." in parts or "\\" in parts[0]:
            continue  # not "<term>/<course>" inside root
        counts[parts[0]] += 1
    if not counts:
        return root
    return root / max(counts, key=lambda term: (counts[term], _term_age(term), term))


def current_term_folder(config: Config) -> Path:
    """``term_folder`` for the saved state and the Courses page's ticks."""
    from blackboard_sync.courses import load_disabled
    from blackboard_sync.state import State

    return term_folder(config.root, State.load(config.state_file, backup=False).courses, load_disabled(config))


# -- where the tools are ---------------------------------------------------------------------------

SHELL_TIMEOUT = 3.0  # seconds the login shell gets to answer ``command -v``
# Where the installers put the programs on macOS, after the login shell's PATH.
MACOS_DIRS = ("~/.local/bin", "~/.claude/local", "/opt/homebrew/bin", "/usr/local/bin", "~/.npm-global/bin",
              "~/.bun/bin", "~/.volta/bin")
NVM_DIR = "~/.nvm/versions/node"  # one bin folder per installed Node version; the newest wins
WINDOWS_EXTENSIONS = ".COM;.EXE;.BAT;.CMD"  # PATHEXT when it is not set


def _expand(path: str, home: Path) -> Path:
    return home / path[2:] if path.startswith("~/") else Path(path)


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _version_key(path: Path) -> tuple[int, ...]:
    """``v22.11.0`` -> (22, 11, 0), for picking the newest Node version."""
    return tuple(int(part) if part.isdigit() else -1 for part in path.name.lstrip("v").split("."))


def shell_paths(output: str) -> dict[str, Path]:
    """The tools ``command -v claude gemini codex`` printed as programs.

    A function or alias prints its name (or its definition), not a path: it is left out, and the
    install folders are searched for it instead.
    """
    found: dict[str, Path] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("/"):
            continue
        path = Path(line)
        if path.name in AI_CLIS and path.name not in found:
            found[path.name] = path
    return found


def _detect_macos(env: Mapping[str, str], home: Path, run: Callable[..., subprocess.CompletedProcess]
                  ) -> dict[str, Path | None]:
    shell = env.get("SHELL") or "/bin/zsh"
    if not os.path.isabs(shell):
        shell = "/bin/zsh"
    found: dict[str, Path] = {}
    try:
        result = run([shell, "-lic", "command -v " + " ".join(AI_CLIS)], capture_output=True, text=True,
                     errors="replace", timeout=SHELL_TIMEOUT, stdin=subprocess.DEVNULL)
        found = {key: path for key, path in shell_paths(result.stdout or "").items() if _executable(path)}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.info("Could not ask the login shell where the AI tools are: %s", exc)
    dirs = [_expand(path, home) for path in MACOS_DIRS]
    try:
        nvm = sorted((version / "bin" for version in _expand(NVM_DIR, home).iterdir()),
                     key=lambda folder: _version_key(folder.parent), reverse=True)
    except OSError:
        nvm = []
    for key in AI_CLIS:
        if key not in found:
            path = next((folder / key for folder in (*dirs, *nvm) if _executable(folder / key)), None)
            if path is not None:
                found[key] = path
    return {key: found.get(key) for key in AI_CLIS}


def windows_find(name: str, dirs: Collection[str | Path], extensions: str) -> Path | None:
    """``shutil.which`` for Windows, testable anywhere: ``name`` plus each PATHEXT extension in ``dirs``."""
    for folder in dirs:
        if not folder:
            continue
        for extension in extensions.split(";"):
            if not extension:
                continue
            candidate = Path(folder) / (name + extension.lower())
            # App execution aliases (``wt.exe`` in WindowsApps) are links that stat may not follow.
            if candidate.is_file() or (os.path.lexists(candidate) and not candidate.is_dir()):
                return candidate
    return None


def _windows_dirs(env: Mapping[str, str], home: Path) -> list[str]:
    dirs = [part.strip().strip('"') for part in (env.get("PATH") or env.get("Path") or "").split(";")]
    profile = env.get("USERPROFILE") or str(home)
    dirs.append(str(Path(profile) / ".local" / "bin"))  # Claude Code's installer
    if env.get("APPDATA"):
        dirs.append(str(Path(env["APPDATA"]) / "npm"))  # npm's global shims (gemini.cmd, codex.cmd)
    return dirs


def _detect_windows(env: Mapping[str, str], home: Path) -> dict[str, Path | None]:
    dirs = _windows_dirs(env, home)
    extensions = env.get("PATHEXT") or WINDOWS_EXTENSIONS
    return {key: windows_find(key, dirs, extensions) for key in AI_CLIS}


def detect(platform: str | None = None, env: Mapping[str, str] | None = None, home: Path | None = None,
           run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict[str, Path | None]:
    """Each tool's program, or None when it is not installed."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    if is_windows(platform):
        return _detect_windows(env, home)
    return _detect_macos(env, home, run)


class Detector:
    """``detect``, remembered for the app's session: Settings shows the last answer at once.

    ``refresh`` runs the search (up to ``SHELL_TIMEOUT`` on macOS) and is meant for a worker
    thread: when Settings opens and before each launch.
    """

    def __init__(self, find: Callable[[], dict[str, Path | None]] = detect):
        self._find = find
        self._lock = threading.Lock()
        self._found: dict[str, Path | None] | None = None

    def cached(self) -> dict[str, Path | None] | None:
        """The last answer; None before the first search."""
        with self._lock:
            return None if self._found is None else dict(self._found)

    def installed(self) -> frozenset[str] | None:
        """The tools found by the last search; None before the first search."""
        found = self.cached()
        return None if found is None else frozenset(key for key, path in found.items() if path)

    def refresh(self) -> dict[str, Path | None]:
        found = self._find()
        with self._lock:
            self._found = dict(found)
        return dict(found)


DETECTOR = Detector()


# -- what runs -------------------------------------------------------------------------------------

def _command(program: PurePath, args: tuple[str, ...], quote: Callable[[str], str]) -> str:
    return " ".join(quote(part) for part in (str(program), *args))


def macos_script(folder: Path, program: Path, tool: AiTool, resume: bool, notice: str = "") -> str:
    """The ``.command`` file Terminal runs: go to ``folder`` and start the tool.

    It deletes itself first (Terminal has it open by then). The program's folder goes first in
    ``PATH``, so a tool installed with npm under nvm finds its ``node``.
    """
    q = shlex.quote
    fresh = _command(program, tool.fresh, q)
    lines = [
        "#!/bin/zsh -l",
        'rm -f -- "$0"',
        f'export PATH={q(str(program.parent))}:"$PATH"',
        f"cd -- {q(str(folder))} || exit 1",
    ]
    if not resume:
        lines.append(f"exec {fresh}")
    else:
        lines += [
            "start=$SECONDS",
            _command(program, tool.resume, q),
            "rc=$?",
            f'if [ "$rc" -ne 0 ] && [ $((SECONDS - start)) -lt {FALLBACK_SECONDS} ]; then',
            f"  printf '%s\\n' {q(notice or T_NO_SESSION)}",
            f"  exec {fresh}",
            "fi",
        ]
    return "\n".join(lines) + "\n"


def macos_commands(script: Path) -> list[str]:
    """Opens ``script`` in a new Terminal window; needs no Automation (AppleScript) permission."""
    return ["/usr/bin/open", "-a", "Terminal", str(script)]


# PowerShell treats these as single quotes too; inside a single-quoted string each is doubled.
_PS_QUOTES = "'\u2018\u2019\u201a\u201b"


def ps_quote(text: str) -> str:
    """``text`` as a single-quoted PowerShell string: nothing in it is expanded or run."""
    return "'" + "".join(c * 2 if c in _PS_QUOTES else c for c in text) + "'"


def windows_script(folder: PurePath | str, program: PurePath | str, tool: AiTool, resume: bool,
                   notice: str = "") -> str:
    """The PowerShell commands the new terminal runs: go to ``folder`` and start the tool.

    The program's folder goes first in ``PATH``, so an npm shim finds the ``node`` beside it.
    """
    q = ps_quote
    program = PureWindowsPath(str(program))
    fresh = "& " + _command(program, tool.fresh, q)
    lines = [
        f"$env:Path = {q(str(program.parent) + ';')} + $env:Path",
        f"Set-Location -LiteralPath {q(str(folder))} -ErrorAction Stop",
    ]
    if not resume:
        lines.append(fresh)
    else:
        lines += [
            "$bbsyncStart = Get-Date",
            "& " + _command(program, tool.resume, q),
            f"if ($LASTEXITCODE -ne 0 -and ((Get-Date) - $bbsyncStart).TotalSeconds -lt {FALLBACK_SECONDS}) {{",
            f"    Write-Host {q(notice or T_NO_SESSION)}",
            f"    {fresh}",
            "}",
        ]
    return "\n".join(lines) + "\n"


def encode_powershell(script: str) -> str:
    """``-EncodedCommand``'s value: base64 of the UTF-16LE text (only letters, digits, ``+/=``)."""
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def windows_commands(script: str, terminal: Path | None, system_root: str) -> list[list[str]]:
    """The commands to try in order: Windows Terminal when there is one, else a PowerShell console.

    Only the base64 script carries the folder and the program, so ``wt.exe``'s own parsing
    (``;`` separates its commands) and ``cmd.exe`` never see them.
    """
    powershell = [str(PureWindowsPath(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")),
                  "-NoLogo", "-NoProfile", "-NoExit", "-EncodedCommand", encode_powershell(script)]
    commands = [[str(terminal), "new-tab", *powershell]] if terminal else []
    return commands + [powershell]


# -- launching -------------------------------------------------------------------------------------

LAUNCH_DIR = "ai-launch"  # in the data folder: the macOS scripts until Terminal runs them
STALE_SCRIPT_SECONDS = 3600
OPEN_TIMEOUT = 15.0
# CreateProcess flags (winbase.h).
DETACHED_PROCESS, CREATE_NEW_CONSOLE = 0x00000008, 0x00000010


def _write_script(data_dir: Path, text: str, now: float) -> Path:
    folder = make_private_dir(data_dir / LAUNCH_DIR)
    for old in folder.glob("bbsync-ai-*.command"):  # Terminal never ran it (or never deleted it)
        try:
            if now - old.stat().st_mtime > STALE_SCRIPT_SECONDS:
                old.unlink()
        except OSError:
            pass
    path = folder / f"bbsync-ai-{uuid.uuid4().hex}.command"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _open_macos(data_dir: Path, folder: Path, program: Path, tool: AiTool, resume: bool,
                run: Callable[..., subprocess.CompletedProcess]) -> str:
    """Starts Terminal; "" when it opened, else the error."""
    try:
        script = _write_script(data_dir, macos_script(folder, program, tool, resume), time.time())
    except OSError as exc:
        return str(exc)
    try:
        result = run(macos_commands(script), capture_output=True, text=True, errors="replace",
                     timeout=OPEN_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        error = str(exc)
    else:
        if result.returncode == 0:
            return ""
        error = (result.stderr or "").strip() or f"open exited with status {result.returncode}"
    try:
        script.unlink()
    except OSError:
        pass
    return error


def _open_windows(folder: Path, program: Path, tool: AiTool, resume: bool, env: Mapping[str, str],
                  home: Path, spawn: Callable[..., object]) -> str:
    """Starts Windows Terminal, else a PowerShell console; "" when one started, else the error."""
    dirs = _windows_dirs(env, home)
    if env.get("LOCALAPPDATA"):
        dirs.append(str(Path(env["LOCALAPPDATA"]) / "Microsoft" / "WindowsApps"))
    terminal = windows_find("wt", dirs, ".exe")
    script = windows_script(folder, program, tool, resume)
    error = ""
    for argv in windows_commands(script, terminal, env.get("SystemRoot") or env.get("SYSTEMROOT") or r"C:\Windows"):
        flags = DETACHED_PROCESS if argv[0] == str(terminal) else CREATE_NEW_CONSOLE
        try:
            spawn(argv, cwd=str(folder), creationflags=flags, close_fds=True)
            return ""
        except (OSError, ValueError) as exc:
            log.info("Could not start %s: %s", Path(argv[0]).name, exc)
            error = str(exc)
    return error


def launch(ai_cli: str, resume: bool, config: Config, detector: Detector = DETECTOR,
           platform: str | None = None, env: Mapping[str, str] | None = None, home: Path | None = None,
           run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
           spawn: Callable[..., object] = subprocess.Popen) -> LaunchResult:
    """Open the current term's folder in a terminal with ``ai_cli`` (``Settings.ai_cli``) running.

    ``resume`` is ``Settings.ai_resume``. Looks for the tool again first (``detector.refresh``),
    so call it from a worker thread. Opens nothing when no tool is chosen, the tool is not
    installed or the folder is not there; the result says which. When the terminal fails, the
    caller can open ``LaunchResult.folder`` in Finder or Explorer instead.
    """
    tool = TOOLS.get(ai_cli)
    if tool is None:
        return LaunchResult(Failure.NO_AI)
    program = detector.refresh().get(tool.key)
    if program is None:
        return LaunchResult(Failure.CLI_MISSING, tool)
    folder = current_term_folder(config)
    if not folder.is_dir():
        return LaunchResult(Failure.FOLDER_MISSING, tool, folder)
    env = os.environ if env is None else env
    home = Path.home() if home is None else home
    if is_windows(platform or sys.platform):
        error = _open_windows(folder, program, tool, resume, env, home, spawn)
    else:
        error = _open_macos(config.data_dir, folder, program, tool, resume, run)
    if error:
        log.warning("Could not open a terminal for %s: %s", tool.name, error)
        return LaunchResult(Failure.TERMINAL_FAILED, tool, folder, error)
    log.info("Opened %s in a terminal", tool.name)
    return LaunchResult(None, tool, folder)
