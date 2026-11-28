"""Open the current term's folder in a terminal and start the AI tool the student clicked.

Home's AI study session card shows one button per installed tool (Claude Code, Gemini CLI,
Codex, Antigravity). Settings → AI assistant chooses which terminal opens
(``Settings.ai_terminal``) and whether the tool continues its last session in the folder
(``Settings.ai_resume``). The card and the menu bar / tray item call ``launch``, which answers
with a ``LaunchResult``: the terminal opened, or why not (``Failure``). Everything else here
is plain logic, testable without a GUI or a terminal:

- ``term_folder``: which folder opens (the term most ticked courses are in, never "No term").
- ``detect``: where each tool is installed. A GUI app does not get the shell's ``PATH`` (on
  macOS launchd gives ``/usr/bin:/bin:/usr/sbin:/sbin``), so macOS asks the student's login
  shell and then looks in the usual install folders; Windows searches ``PATH`` with
  ``PATHEXT`` plus the folders the installers use.
- ``detect_terminals`` / ``resolve_terminal``: which terminals are there, and the one to use
  (the system's own when none is chosen or the chosen one is gone).
- ``macos_script`` / ``windows_script`` and the ``*_commands`` builders: what runs.

The folder name comes from Blackboard (the term's name), so it never reaches a shell as it is:
on macOS every value in the script is quoted with ``shlex.quote`` and a terminal gets the
script's path as one argument (quoted with ``shlex.quote`` where a shell reads it); on Windows
the script is handed to PowerShell as ``-EncodedCommand`` (base64), so neither ``wt.exe`` nor
``cmd.exe`` parses any of it, and every value inside is a single-quoted PowerShell string.

Warp is not offered: its ``warp://`` links cannot run a command, and the other way in is
writing a configuration file into Warp's own folder.

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

from blackboard_sync import licensing
from blackboard_sync.config import Config
from blackboard_sync.i18n import tr
from blackboard_sync.settings import (
    AI_AGY,
    AI_CLAUDE,
    AI_CLIS,
    AI_CODEX,
    AI_GEMINI,
    MACOS_AI_TERMINALS,
    WINDOWS_AI_TERMINALS,
)
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
# recent"; its sessions are per project folder. Verified 2026-11-27: ``agy --help``:
# "-c  Short alias for --continue", "--continue  Continue the most recent conversation".
TOOLS = {tool.key: tool for tool in (
    AiTool(AI_CLAUDE, "Claude Code", ("--continue",), "https://code.claude.com/docs/en/setup"),
    AiTool(AI_GEMINI, "Gemini CLI", ("--resume", "latest"), "https://github.com/google-gemini/gemini-cli"),
    AiTool(AI_CODEX, "Codex", ("resume", "--last"), "https://github.com/openai/codex"),
    AiTool(AI_AGY, "Antigravity", ("--continue",), "https://antigravity.google/docs/getting-started?tab=cli"),
)}
assert tuple(TOOLS) == AI_CLIS

# The vendors' marks for the buttons (``ai_logos/README.md`` says where each comes from).
LOGO_DIR = Path(__file__).with_name("ai_logos")
NOTEBOOK_LOGO = LOGO_DIR / "gemini-notebook.png"  # beside the title of Home's notebook card


def logo_path(key: str, dark: bool = False) -> Path:
    """The tool's logo; ``dark`` asks for the one drawn on a dark background, where there is one."""
    inverted = LOGO_DIR / f"{key}-dark.png"
    return inverted if dark and inverted.is_file() else LOGO_DIR / f"{key}.png"


def preferred_tool(last: str, installed: Collection[str] | None) -> AiTool | None:
    """What the menu item opens: the tool used last, else the first installed one.

    ``installed`` is ``Detector.installed()``; before the first search (None) it is the one
    used last. None when there is nothing to open.
    """
    if installed is None or last in installed:
        return TOOLS.get(last)
    return next((TOOLS[key] for key in AI_CLIS if key in installed), None)


@dataclass(frozen=True)
class Terminal:
    key: str  # settings.AI_TERMINALS
    name: str  # as the vendor writes it
    app: str = ""  # macOS: the application's folder name


TERMINALS = {terminal.key: terminal for terminal in (
    Terminal("terminal", "Terminal", "Terminal.app"),
    Terminal("iterm2", "iTerm2", "iTerm.app"),
    Terminal("ghostty", "Ghostty", "Ghostty.app"),
    Terminal("wezterm", "WezTerm", "WezTerm.app"),
    Terminal("kitty", "kitty", "kitty.app"),
    Terminal("alacritty", "Alacritty", "Alacritty.app"),
    Terminal("windows_terminal", "Windows Terminal"),
    Terminal("powershell", "PowerShell"),
    Terminal("cmd", tr("Command Prompt")),
)}
assert tuple(TERMINALS) == MACOS_AI_TERMINALS + WINDOWS_AI_TERMINALS

# A resume command that fails sooner than this found no session to continue: start a new one.
FALLBACK_SECONDS = 5
T_NO_SESSION = tr("No earlier session here, starting a new one.")


class Failure(enum.Enum):
    """Why ``launch`` opened no terminal."""

    NO_AI = "no_ai"  # no known tool was asked for
    CLI_MISSING = "cli_missing"  # the tool is not installed (``LaunchResult.tool`` names it)
    FOLDER_MISSING = "folder_missing"  # the term folder is not on disk yet (``LaunchResult.folder``)
    TERMINAL_FAILED = "terminal_failed"  # the terminal did not start (``LaunchResult.error``)


@dataclass(frozen=True)
class LaunchResult:
    failure: Failure | None = None  # None: the terminal opened (or the command was copied in MAS)
    tool: AiTool | None = None
    folder: Path | None = None  # the term folder, once known
    error: str = ""  # what the terminal reported, for TERMINAL_FAILED
    terminal: Terminal | None = None  # the one used, once chosen
    copied_command: str = ""  # non-empty when the command was copied to the clipboard (MAS)

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


def term_folder(root: Path, courses: Mapping[str, object], disabled: Collection[str] = (),
                platform: str | None = None) -> Path:
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
        if len(parts) < 2 or folder.startswith("/") or ".." in parts:
            continue  # not "<term>/<course>" inside root
        if is_windows(platform) and ("\\" in parts[0] or ":" in parts[0]):
            continue  # a separator or drive there (a backslash is an ordinary character on macOS)
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


def _detect_macos(env: Mapping[str, str], home: Path, run: Callable[..., subprocess.CompletedProcess],
                  dirs: Collection[str] = MACOS_DIRS) -> dict[str, Path | None]:
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
    folders = [_expand(path, home) for path in dirs]
    try:
        nvm = sorted((version / "bin" for version in _expand(NVM_DIR, home).iterdir()),
                     key=lambda folder: _version_key(folder.parent), reverse=True)
    except OSError:
        nvm = []
    for key in AI_CLIS:
        if key not in found:
            path = next((folder / key for folder in (*folders, *nvm) if _executable(folder / key)), None)
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
    if env.get("LOCALAPPDATA"):
        dirs.append(str(Path(env["LOCALAPPDATA"]) / "agy" / "bin"))  # Antigravity's installer
    return dirs


def _detect_windows(env: Mapping[str, str], home: Path) -> dict[str, Path | None]:
    dirs = _windows_dirs(env, home)
    extensions = env.get("PATHEXT") or WINDOWS_EXTENSIONS
    return {key: windows_find(key, dirs, extensions) for key in AI_CLIS}


def detect(platform: str | None = None, env: Mapping[str, str] | None = None, home: Path | None = None,
           run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
           dirs: Collection[str] = MACOS_DIRS) -> dict[str, Path | None]:
    """Each tool's program, or None when it is not installed; ``dirs`` are macOS's install folders.

    In Mac App Store (``mas``) builds, App Sandbox blocks inspecting host shell PATHs and
    launching terminals via ``osascript``; all four tools are offered as Copy-command actions.
    """
    env = os.environ if env is None else env
    if licensing.is_mas(platform=platform, env=env):
        return {key: Path(key) for key in AI_CLIS}
    home = Path.home() if home is None else home
    if is_windows(platform):
        return _detect_windows(env, home)
    return _detect_macos(env, home, run, dirs)


class Detector:
    """``detect`` or ``detect_terminals``, remembered for the app's session: Home shows the last
    answer at once.

    ``refresh`` runs the search (up to ``SHELL_TIMEOUT`` for the tools on macOS) and is meant
    for a worker thread: when the app starts, when Home opens and before each launch.
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


# -- which terminals there are ---------------------------------------------------------------------

# Where macOS applications are; Terminal.app is in the last one.
MACOS_APP_DIRS = ("/Applications", "~/Applications", "/Applications/Utilities", "/System/Applications/Utilities")


def _system_root(env: Mapping[str, str]) -> str:
    return env.get("SystemRoot") or env.get("SYSTEMROOT") or r"C:\Windows"


def detect_terminals(platform: str | None = None, env: Mapping[str, str] | None = None, home: Path | None = None,
                     app_dirs: Collection[str] = MACOS_APP_DIRS) -> dict[str, Path | None]:
    """Each of the platform's terminals: its application or program, or None when it is not there."""
    env = os.environ if env is None else env
    if licensing.is_mas(platform=platform, env=env):
        return {}
    home = Path.home() if home is None else home
    if is_windows(platform):
        dirs = _windows_dirs(env, home)
        if env.get("LOCALAPPDATA"):
            dirs.append(str(Path(env["LOCALAPPDATA"]) / "Microsoft" / "WindowsApps"))
        system32 = Path(_system_root(env), "System32")
        found = {"windows_terminal": windows_find("wt", dirs, ".exe")}
        for key, path in (("powershell", system32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
                          ("cmd", system32 / "cmd.exe")):
            found[key] = path if path.is_file() else None
        return found
    folders = [_expand(path, home) for path in app_dirs]
    found = {key: next((folder / TERMINALS[key].app for folder in folders
                        if (folder / TERMINALS[key].app).is_dir()), None)
             for key in MACOS_AI_TERMINALS}
    if found["terminal"] is None:  # part of macOS: ``open -a Terminal`` finds it wherever it is
        found["terminal"] = Path("/System/Applications/Utilities/Terminal.app")
    return found


def system_terminal(installed: Collection[str]) -> str:
    """The terminal used when none is chosen: Terminal on macOS; on Windows, Windows Terminal
    when there is one, else PowerShell."""
    return next((key for key in ("terminal", "windows_terminal") if key in installed), "powershell")


def resolve_terminal(choice: str, installed: Collection[str]) -> str:
    """The terminal to use for ``Settings.ai_terminal``: the chosen one while it is installed,
    else the system's own."""
    return choice if choice in installed else system_terminal(installed)


TERMINAL_DETECTOR = Detector(detect_terminals)


# -- what runs -------------------------------------------------------------------------------------

def _command(program: PurePath, args: tuple[str, ...], quote: Callable[[str], str]) -> str:
    return " ".join(quote(part) for part in (str(program), *args))


def _macos_session_lines(program: PurePath, tool: AiTool, resume: bool, notice: str = "") -> list[str]:
    q = shlex.quote
    fresh = _command(program, tool.fresh, q)
    if not resume:
        return [f"exec {fresh}"]
    return [
        "start=$SECONDS",
        _command(program, tool.resume, q),
        "rc=$?",
        f'if [ "$rc" -ne 0 ] && [ $((SECONDS - start)) -lt {FALLBACK_SECONDS} ]; then',
        f"  printf '%s\\n' {q(notice or T_NO_SESSION)}",
        f"  exec {fresh}",
        "fi",
    ]


def macos_script(folder: Path, program: Path, tool: AiTool, resume: bool, notice: str = "") -> str:
    """The ``.command`` file Terminal runs: go to ``folder`` and start the tool.

    It deletes itself first (Terminal has it open by then). The program's folder goes first in
    ``PATH``, so a tool installed with npm under nvm finds its ``node``.
    """
    q = shlex.quote
    lines = [
        "#!/bin/zsh -l",
        'rm -f -- "$0"',
        f'export PATH={q(str(program.parent))}:"$PATH"',
        f"cd -- {q(str(folder))} || exit 1",
        *_macos_session_lines(program, tool, resume, notice),
    ]
    return "\n".join(lines) + "\n"


# Types the command into a new iTerm2 window; the text arrives as an argument, never as AppleScript.
ITERM_SCRIPT = (
    "on run argv",
    'tell application id "com.googlecode.iterm2"',
    "activate",
    "set newWindow to (create window with default profile)",
    "tell current session of newWindow to write text (item 1 of argv)",
    "end tell",
    "end run",
)


def macos_commands(script: Path, terminal: str = "terminal", app: Path | None = None,
                   folder: Path | None = None) -> list[str]:
    """Opens ``script`` in a new window of ``terminal``.

    Terminal opens the script itself and needs no Automation (AppleScript) permission; iTerm2 is
    asked through AppleScript, so macOS asks the student once. The others (``app``, their
    application) take a start folder and a program: a login shell that loads the student's setup,
    as Terminal's does, and then runs the script.
    """
    if terminal == "terminal":
        return ["/usr/bin/open", "-a", "Terminal", str(script)]
    if terminal == "iterm2":
        lines = [part for line in ITERM_SCRIPT for part in ("-e", line)]
        return ["/usr/bin/osascript", *lines, "exec " + shlex.quote(str(script))]
    shell = ["/bin/zsh", "-ilc", "exec " + shlex.quote(str(script))]
    options = {
        "ghostty": [f"--working-directory={folder}", "-e", *shell],
        "wezterm": ["start", "--cwd", str(folder), "--", *shell],
        "kitty": ["--directory", str(folder), *shell],
        "alacritty": ["--working-directory", str(folder), "-e", *shell],
    }[terminal]
    return ["/usr/bin/open", "-na", str(app), "--args", *options]


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


def windows_commands(script: str, terminal: str, wt: Path | None, system_root: str) -> list[str]:
    """The command that opens ``script`` in ``terminal``; ``wt`` is Windows Terminal's program.

    Only the base64 script carries the folder and the program, so ``wt.exe``'s own parsing
    (``;`` separates its commands) and ``cmd.exe`` never see them. In Command Prompt the prompt
    stays once the tool ends; the other two keep PowerShell open.
    """
    system32 = PureWindowsPath(system_root, "System32")
    powershell = [str(system32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"), "-NoLogo", "-NoProfile"]
    encoded = ["-EncodedCommand", encode_powershell(script)]
    if terminal == "cmd":
        return [str(system32 / "cmd.exe"), "/k", *powershell, *encoded]
    command = [*powershell, "-NoExit", *encoded]
    return [str(wt), "new-tab", *command] if terminal == "windows_terminal" else command


# -- launching -------------------------------------------------------------------------------------

LAUNCH_DIR = "ai-launch"  # in the data folder: the macOS scripts until Terminal runs them
STALE_SCRIPT_SECONDS = 3600
OPEN_TIMEOUT = 15.0
AUTOMATION_TIMEOUT = 120.0  # iTerm2's first launch waits while macOS asks for permission
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


def _open_macos(data_dir: Path, folder: Path, program: Path, tool: AiTool, resume: bool, terminal: str,
                app: Path | None, run: Callable[..., subprocess.CompletedProcess]) -> str:
    """Starts the terminal; "" when it opened, else the error."""
    try:
        script = _write_script(data_dir, macos_script(folder, program, tool, resume), time.time())
    except OSError as exc:
        return str(exc)
    argv = macos_commands(script, terminal, app, folder)
    timeout = AUTOMATION_TIMEOUT if terminal == "iterm2" else OPEN_TIMEOUT
    try:
        result = run(argv, capture_output=True, text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        error = str(exc)
    else:
        if result.returncode == 0:
            return ""
        error = ((result.stderr or "").strip()
                 or f"{Path(argv[0]).name} exited with status {result.returncode}")
    try:
        script.unlink()
    except OSError:
        pass
    return error


def _open_windows(folder: Path, program: Path, tool: AiTool, resume: bool, terminals: list[str], wt: Path | None,
                  env: Mapping[str, str], spawn: Callable[..., object]) -> str:
    """Starts the first of ``terminals`` that will; "" when one started, else the error."""
    script = windows_script(folder, program, tool, resume)
    error = ""
    for terminal in terminals:
        argv = windows_commands(script, terminal, wt, _system_root(env))
        flags = DETACHED_PROCESS if terminal == "windows_terminal" else CREATE_NEW_CONSOLE
        try:
            spawn(argv, cwd=str(folder), creationflags=flags, close_fds=True)
            return ""
        except (OSError, ValueError) as exc:
            log.info("Could not start %s: %s", TERMINALS[terminal].name, exc)
            error = str(exc)
    return error


def copy_command_text(folder: PurePath, tool: AiTool, resume: bool = False) -> str:
    """Shell command pasted into the student's terminal, where their PATH is already set."""
    program = PurePosixPath(tool.key)
    cd = f"cd -- {shlex.quote(str(folder))}"
    if not resume:
        return f"{cd} && {_command(program, tool.fresh, shlex.quote)}"
    # A child zsh provides SECONDS and contains exec, leaving the terminal's shell open.
    session = "; ".join(line.strip() for line in _macos_session_lines(program, tool, resume))
    return f"{cd} && {shlex.join(('/bin/zsh', '-c', session))}"


def copy_to_clipboard(text: str) -> bool:
    """Copy ``text`` to the macOS pasteboard without spawning external processes."""
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString

        board = NSPasteboard.generalPasteboard()
        board.clearContents()
        return bool(board.setString_forType_(text, NSPasteboardTypeString))
    except Exception as exc:
        log.warning("Could not copy AI command to pasteboard: %s", exc)
        return False


def copy_command(
    ai_cli: str,
    config: Config,
    copy_fn: Callable[[str], bool] = copy_to_clipboard,
    *,
    resume: bool = False,
) -> LaunchResult:
    """Copy the command for Mac App Store builds."""
    tool = TOOLS.get(ai_cli)
    if tool is None:
        return LaunchResult(Failure.NO_AI)
    folder = current_term_folder(config)
    if not folder.is_dir():
        return LaunchResult(Failure.FOLDER_MISSING, tool, folder)
    command = copy_command_text(folder, tool, resume)
    if not copy_fn(command):
        return LaunchResult(Failure.TERMINAL_FAILED, tool, folder, error=tr("Could not copy the command."))
    return LaunchResult(None, tool, folder, copied_command=command)


def open_mas_terminal(folder: Path, terminal: str = "") -> None:
    """Ask Launch Services to open a folder in a terminal, without sending a command."""
    def completed(_app, error):
        if error is not None:
            log.warning("Could not open a terminal for the copied AI command: %s", error)

    try:
        from AppKit import NSWorkspace, NSWorkspaceOpenConfiguration
        from Foundation import NSURL

        workspace = NSWorkspace.sharedWorkspace()
        app_url = None
        # iTerm2 also starts a shell when handed a directory URL.
        if terminal == "iterm2":
            app_url = workspace.URLForApplicationWithBundleIdentifier_("com.googlecode.iterm2")
        if app_url is None:
            app_url = workspace.URLForApplicationWithBundleIdentifier_("com.apple.Terminal")
        if app_url is not None:
            workspace.openURLs_withApplicationAtURL_configuration_completionHandler_(
                [NSURL.fileURLWithPath_isDirectory_(str(folder), True)],
                app_url, NSWorkspaceOpenConfiguration.configuration(), completed,
            )
    except Exception:
        log.exception("Could not open a terminal for the copied AI command")


def launch(ai_cli: str, resume: bool, config: Config, detector: Detector = DETECTOR,
           platform: str | None = None, env: Mapping[str, str] | None = None,
           run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
           spawn: Callable[..., object] = subprocess.Popen, terminal: str = "",
           terminals: Detector = TERMINAL_DETECTOR,
           copy_fn: Callable[[str], bool] = copy_to_clipboard) -> LaunchResult:
    """Open the current term's folder in a terminal with ``ai_cli`` running.

    ``resume`` is ``Settings.ai_resume`` and ``terminal`` ``Settings.ai_terminal`` ("" or one
    that is gone: the system's own). Looks for the tool and the terminals again first, so call
    it from a worker thread. Opens nothing when no known tool is asked for, the tool is not
    installed or the folder is not there; the result says which. When the terminal fails, the
    caller can open ``LaunchResult.folder`` in Finder or Explorer instead.

    In Mac App Store (``mas``) builds, App Sandbox does not allow launching terminals via
    ``osascript``. Copy the session command to the clipboard so the student can run it in the
    terminal. The macOS AI card opens the folder after the copy.
    """
    env = os.environ if env is None else env
    if licensing.is_mas(platform=platform, env=env):
        return copy_command(ai_cli, config, copy_fn=copy_fn, resume=resume)
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
    windows = is_windows(platform or sys.platform)
    keys = WINDOWS_AI_TERMINALS if windows else MACOS_AI_TERMINALS
    found = {key: path for key, path in terminals.refresh().items() if path and key in keys}
    used = TERMINALS[resolve_terminal(terminal, found)]
    if windows:
        wanted = [used.key]
        if used.key == "windows_terminal" and terminal != used.key:
            wanted.append("powershell")  # nothing was chosen: a console will do
        error = _open_windows(folder, program, tool, resume, wanted, found.get("windows_terminal"), env, spawn)
    else:
        error = _open_macos(config.data_dir, folder, program, tool, resume, used.key, found.get(used.key), run)
    if error:
        log.warning("Could not open %s for %s: %s", used.name, tool.name, error)
        return LaunchResult(Failure.TERMINAL_FAILED, tool, folder, error, used)
    log.info("Opened %s in %s", tool.name, used.name)
    return LaunchResult(None, tool, folder, terminal=used)
