"""Opening the term folder in a terminal with the chosen AI tool (``ai_launcher``).

No terminal, AI tool or PowerShell is started: the process calls are fakes. The macOS script is
run for real by zsh (when there is one) against a stand-in program that only records how it
was called, so the quoting and the resume-then-new-session fallback are proven, not just read.
"""

from __future__ import annotations

import base64
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from blackboard_sync import ai_launcher as ai
from blackboard_sync.config import Config
from blackboard_sync.courses import save_disabled
from blackboard_sync.settings import AI_TERMINALS, MACOS_AI_TERMINALS, WINDOWS_AI_TERMINALS
from blackboard_sync.state import State

GUZ = "2026-2027 Güz"
BAHAR = "2025-2026 Bahar"
QUOTED = "Ali'nin Dönemi"  # a term name with a single quote
HOSTILE = "$(touch pwned); `id` & \"x\" %PATH% ’q’"  # nothing in it may run or expand


def course(term: str, name: str = "MAT101 Calculus", **extra) -> dict:
    return {"code": name.split()[0], "title": name, "term": term, "folder": f"{term}/{name}", **extra}


# -- which folder ----------------------------------------------------------------------------------

def test_the_term_with_the_most_ticked_courses_is_opened(tmp_path):
    courses = {
        "_1_1": course(GUZ, "MAT101 Calculus"),
        "_2_1": course(GUZ, "PHY101 Physics"),
        "_3_1": course(BAHAR, "CHE101 Chemistry"),
    }
    assert ai.term_folder(tmp_path, courses) == tmp_path / GUZ
    # Unticked courses do not count: Bahar now has more.
    courses["_4_1"] = course(BAHAR, "BIO101 Biology")
    assert ai.term_folder(tmp_path, courses, disabled={"_1_1"}) == tmp_path / BAHAR


def test_courses_without_a_term_never_choose_the_folder(tmp_path):
    courses = {
        "_1_1": course(GUZ),
        "_2_1": course("No term", "PDR01 Rehberlik"),
        "_3_1": course("No term", "ORY01 Oryantasyon"),
        "_4_1": {**course("Okul", "LIB100 Library"), "termless": True},  # marked by a newer version
        "_5_1": {"code": "X", "term": "Term 5", "folder": "No term/X"},
    }
    assert ai.term_folder(tmp_path, courses) == tmp_path / GUZ
    # Only termless courses (or none ticked): the University folder itself.
    assert ai.term_folder(tmp_path, {k: v for k, v in courses.items() if k != "_1_1"}) == tmp_path
    assert ai.term_folder(tmp_path, courses, disabled={"_1_1"}) == tmp_path


def test_a_tie_goes_to_the_newer_term(tmp_path):
    courses = {"_1_1": course(BAHAR), "_2_1": course(GUZ)}
    assert ai.term_folder(tmp_path, courses) == tmp_path / GUZ
    courses = {"_1_1": course("Fall 2026"), "_2_1": course("Spring 2026")}
    assert ai.term_folder(tmp_path, courses) == tmp_path / "Fall 2026"


def test_no_courses_yet_opens_the_university_folder(tmp_path):
    assert ai.term_folder(tmp_path, {}) == tmp_path


def test_a_backslash_is_part_of_a_term_name_on_macos_but_a_separator_on_windows(tmp_path):
    courses = {"_1_1": course("Güz\\Fall 2026")}
    assert ai.term_folder(tmp_path, courses, platform="darwin") == tmp_path / "Güz\\Fall 2026"
    assert ai.term_folder(tmp_path, courses, platform="win32") == tmp_path
    assert ai.term_folder(tmp_path, {"_1_1": course("C:x")}, platform="win32") == tmp_path


def test_a_recorded_folder_never_leads_outside_the_university_folder(tmp_path):
    courses = {
        "_1_1": {"term": "x", "folder": "../../etc/x"},
        "_2_1": {"term": "x", "folder": "/etc/passwd"},
        "_3_1": {"term": "x", "folder": "flat"},
        "_4_1": {"term": "x", "folder": 5},
        "_5_1": "not a dict",
    }
    assert ai.term_folder(tmp_path, courses) == tmp_path


def make_config(tmp_path: Path, courses: dict, disabled=()) -> Config:
    config = Config(base_url="https://bb.example.edu", dest=tmp_path / "Drive", data_dir=tmp_path / "data")
    config.ensure_data_dir()
    state = State(config.state_file)
    state.courses, state.dirty = courses, True
    state.save()
    if disabled:
        save_disabled(config, disabled)
    return config


def test_the_current_term_folder_reads_the_saved_state_and_the_ticks(tmp_path):
    config = make_config(tmp_path, {"_1_1": course(GUZ), "_2_1": course(BAHAR), "_3_1": course(BAHAR, "X1 X")},
                         disabled={"_2_1", "_3_1"})
    assert ai.current_term_folder(config) == tmp_path / "Drive" / "University" / GUZ


# -- where the tools are ---------------------------------------------------------------------------

# The installers' folders under the fixture's home; the system ones (/opt/homebrew/bin) are left out.
LOCAL_DIRS = tuple(path for path in ai.MACOS_DIRS if path.startswith("~/"))


def program(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


class ShellAnswer:
    def __init__(self, stdout: str = "", error: Exception | None = None):
        self.stdout, self.error, self.calls = stdout, error, []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(argv, 0, self.stdout, "")


@pytest.mark.skipif(sys.platform == "win32", reason="macOS paths and file modes")
def test_macos_asks_the_login_shell_and_takes_only_real_programs(tmp_path):
    claude = program(tmp_path / "bin" / "claude")
    run = ShellAnswer(f"{claude}\ncodex\nalias gemini='npx gemini'\n/nowhere/gemini\n")
    found = ai.detect("darwin", env={"SHELL": "/bin/zsh"}, home=tmp_path / "home", run=run, dirs=LOCAL_DIRS)
    assert found == {"claude": claude, "gemini": None, "codex": None, "agy": None}
    argv, kwargs = run.calls[0]
    assert argv == ["/bin/zsh", "-lic", "command -v claude gemini codex agy"]
    assert kwargs["timeout"] == ai.SHELL_TIMEOUT and kwargs["stdin"] == subprocess.DEVNULL


@pytest.mark.skipif(sys.platform == "win32", reason="macOS paths and file modes")
def test_macos_looks_in_the_install_folders_for_what_the_shell_did_not_name(tmp_path):
    home = tmp_path / "home"
    # The shell wraps codex in a function, so it prints a name: the install folder has it.
    codex = program(home / ".local" / "bin" / "codex")
    agy = program(home / ".local" / "bin" / "agy")
    program(home / ".nvm" / "versions" / "node" / "v9.0.0" / "bin" / "gemini")
    gemini = program(home / ".nvm" / "versions" / "node" / "v22.11.0" / "bin" / "gemini")
    (home / ".claude" / "local").mkdir(parents=True)
    (home / ".claude" / "local" / "claude").write_text("not executable", encoding="utf-8")
    found = ai.detect("darwin", env={"SHELL": "/bin/zsh"}, home=home, run=ShellAnswer("codex\n"), dirs=LOCAL_DIRS)
    assert found["codex"] == codex
    assert found["agy"] == agy
    assert found["gemini"] == gemini  # the newest Node version
    assert found["claude"] is None


@pytest.mark.skipif(sys.platform == "win32", reason="macOS paths and file modes")
def test_a_shell_that_hangs_or_is_missing_still_finds_the_install_folders(tmp_path):
    home = tmp_path / "home"
    claude = program(home / ".local" / "bin" / "claude")
    agy = program(home / ".local" / "bin" / "agy")
    for error in (subprocess.TimeoutExpired("zsh", 3), FileNotFoundError("zsh")):
        found = ai.detect("darwin", env={"SHELL": "/bin/zsh"}, home=home, run=ShellAnswer(error=error),
                          dirs=LOCAL_DIRS)
        assert found["claude"] == claude and found["agy"] == agy
    # A relative or missing SHELL falls back to zsh.
    run = ShellAnswer()
    ai.detect("darwin", env={"SHELL": "zsh"}, home=home, run=run, dirs=LOCAL_DIRS)
    assert run.calls[0][0][0] == "/bin/zsh"


def test_windows_searches_path_with_pathext_and_the_installers_folders(tmp_path):
    profile, appdata, localappdata = tmp_path / "Users" / "Öğrenci", tmp_path / "Roaming", tmp_path / "Local"
    claude = program(profile / ".local" / "bin" / "claude.exe")
    gemini = program(appdata / "npm" / "gemini.cmd")
    other = program(tmp_path / "tools" / "codex.bat")
    agy = program(localappdata / "agy" / "bin" / "agy.exe")
    env = {"PATH": f'"{tmp_path / "empty"}";{tmp_path / "tools"}', "PATHEXT": ".COM;.EXE;.BAT;.CMD",
           "USERPROFILE": str(profile), "APPDATA": str(appdata), "LOCALAPPDATA": str(localappdata)}
    assert ai.detect("win32", env=env, home=tmp_path) == {
        "claude": claude, "gemini": gemini, "codex": other, "agy": agy,
    }
    # A PATHEXT without .BAT does not run codex.bat.
    assert ai.detect("win32", env={**env, "PATHEXT": ".EXE;.CMD"}, home=tmp_path)["codex"] is None


def test_the_detector_remembers_the_last_answer():
    answers = [{"claude": Path("/x/claude"), "gemini": None, "codex": None},
               {"claude": None, "gemini": None, "codex": Path("/x/codex")}]
    detector = ai.Detector(lambda: answers.pop(0))
    assert detector.cached() is None and detector.installed() is None
    detector.refresh()
    assert detector.installed() == frozenset({"claude"})
    detector.refresh()
    assert detector.installed() == frozenset({"codex"})


# -- the tools' buttons ----------------------------------------------------------------------------

@pytest.mark.parametrize("key", ai.AI_CLIS)
def test_every_tool_has_a_bundled_logo(key):
    for dark in (False, True):
        assert ai.logo_path(key, dark).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_only_codex_has_a_second_logo_for_dark_backgrounds():
    assert ai.logo_path("codex", dark=True).name == "codex-dark.png"
    assert ai.logo_path("claude", dark=True) == ai.logo_path("claude")


@pytest.mark.parametrize("last, installed, expected", [
    ("codex", None, "codex"),  # not looked yet: the one used last
    ("", None, None),
    ("codex", {"claude", "codex"}, "codex"),
    ("gemini", {"claude", "codex"}, "claude"),  # gone: the first that is there
    ("", {"codex"}, "codex"),
    ("claude", set(), None),
])
def test_the_menu_item_opens_the_tool_used_last_while_it_is_installed(last, installed, expected):
    tool = ai.preferred_tool(last, installed if installed is None else frozenset(installed))
    assert (tool.key if tool else None) == expected


# -- which terminals there are ---------------------------------------------------------------------

def installed(found: dict) -> set[str]:
    return {key for key, path in found.items() if path}


def test_macos_lists_the_terminal_applications_that_are_there(tmp_path):
    for app in ("iTerm.app", "kitty.app"):
        (tmp_path / "Applications" / app).mkdir(parents=True)
    (tmp_path / "More" / "Ghostty.app").mkdir(parents=True)
    (tmp_path / "More" / "Warp.app").mkdir()  # not offered: it cannot be told to run a command
    found = ai.detect_terminals("darwin", env={}, home=tmp_path, app_dirs=("~/Applications", str(tmp_path / "More")))
    assert tuple(found) == MACOS_AI_TERMINALS
    assert installed(found) == {"terminal", "iterm2", "ghostty", "kitty"}  # Terminal is part of macOS
    assert found["kitty"] == tmp_path / "Applications" / "kitty.app"


def windows_env(tmp_path: Path, terminal: bool, powershell: bool = True) -> dict:
    apps = tmp_path / "Local" / "Microsoft" / "WindowsApps"
    apps.mkdir(parents=True)
    if terminal:
        program(apps / "wt.exe")
    system32 = tmp_path / "Windows" / "System32"
    program(system32 / "cmd.exe")
    if powershell:
        program(system32 / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    return {"PATH": "", "LOCALAPPDATA": str(tmp_path / "Local"), "SystemRoot": str(tmp_path / "Windows"),
            "USERPROFILE": str(tmp_path)}


@pytest.mark.parametrize("terminal", [True, False])
def test_windows_lists_its_terminals(tmp_path, terminal):
    found = ai.detect_terminals("win32", env=windows_env(tmp_path, terminal), home=tmp_path)
    assert tuple(found) == WINDOWS_AI_TERMINALS
    assert installed(found) == set(WINDOWS_AI_TERMINALS) - (set() if terminal else {"windows_terminal"})


@pytest.mark.parametrize("choice, there, used", [
    ("", {"terminal", "kitty"}, "terminal"),
    ("kitty", {"terminal", "kitty"}, "kitty"),
    ("iterm2", {"terminal", "kitty"}, "terminal"),  # gone: the system's own
    ("", {"windows_terminal", "powershell", "cmd"}, "windows_terminal"),
    ("cmd", {"windows_terminal", "powershell", "cmd"}, "cmd"),
    ("windows_terminal", {"powershell", "cmd"}, "powershell"),
    ("kitty", {"powershell", "cmd"}, "powershell"),  # a choice made on a Mac
])
def test_the_chosen_terminal_is_used_while_it_is_there(choice, there, used):
    assert ai.resolve_terminal(choice, there) == used


def test_every_terminal_has_a_name():
    assert tuple(ai.TERMINALS) == AI_TERMINALS
    assert all(terminal.name for terminal in ai.TERMINALS.values())


# -- how each macOS terminal is opened -------------------------------------------------------------

SCRIPT = PurePosixPath("/Users/me/Library/Application Support/BlackboardSync/ai-launch/bbsync-ai-1.command")
FOLDER = PurePosixPath("/Users/me/University") / HOSTILE
RUN_SCRIPT = f"exec '{SCRIPT}'"
SHELL = ["/bin/zsh", "-ilc", RUN_SCRIPT]


def test_terminal_opens_the_script_itself():
    assert ai.macos_commands(SCRIPT) == ["/usr/bin/open", "-a", "Terminal", str(SCRIPT)]
    assert ai.macos_commands(SCRIPT, "terminal", None, FOLDER) == ai.macos_commands(SCRIPT)


def test_iterm_gets_the_quoted_script_as_an_argument_never_inside_the_applescript():
    argv = ai.macos_commands(SCRIPT, "iterm2", PurePosixPath("/Applications/iTerm.app"), FOLDER)
    assert argv[0] == "/usr/bin/osascript" and argv[-1] == RUN_SCRIPT
    assert argv[1:-1:2] == ["-e"] * len(ai.ITERM_SCRIPT) and tuple(argv[2:-1:2]) == ai.ITERM_SCRIPT
    assert not any(str(SCRIPT) in line for line in ai.ITERM_SCRIPT)


@pytest.mark.parametrize("terminal, options", [
    ("ghostty", [f"--working-directory={FOLDER}", "-e", *SHELL]),
    ("wezterm", ["start", "--cwd", str(FOLDER), "--", *SHELL]),
    ("kitty", ["--directory", str(FOLDER), *SHELL]),
    ("alacritty", ["--working-directory", str(FOLDER), "-e", *SHELL]),
])
def test_the_other_terminals_take_the_folder_as_one_argument_and_a_login_shell(terminal, options):
    app = PurePosixPath("/Applications") / ai.TERMINALS[terminal].app
    argv = ai.macos_commands(SCRIPT, terminal, app, FOLDER)
    assert argv == ["/usr/bin/open", "-na", str(app), "--args", *options]
    assert not any(HOSTILE in part for part in argv[argv.index(SHELL[0]):])  # no shell ever reads the folder


# -- the macOS script ------------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="macOS paths and file modes")
@pytest.mark.parametrize("key", ai.AI_CLIS)
def test_the_macos_script_quotes_everything_and_falls_back_to_a_new_session(key, tmp_path):
    tool = ai.TOOLS[key]
    folder = tmp_path / "University" / QUOTED
    script = ai.macos_script(folder, Path("/Users/me/.local/bin") / key, tool, resume=True, notice="No session")
    lines = script.splitlines()
    assert lines[0] == "#!/bin/zsh -l"
    assert f"cd -- '{tmp_path}/University/Ali'\"'\"'nin Dönemi' || exit 1" in lines
    assert " ".join([f"/Users/me/.local/bin/{key}", *tool.resume]) in lines
    assert f"  exec /Users/me/.local/bin/{key}" in lines
    assert f"[ $((SECONDS - start)) -lt {ai.FALLBACK_SECONDS} ]" in script
    fresh = ai.macos_script(folder, Path("/Users/me/.local/bin") / key, tool, resume=False)
    assert fresh.splitlines()[-1] == f"exec /Users/me/.local/bin/{key}" and "SECONDS" not in fresh


def test_each_tool_resumes_with_its_own_verified_arguments():
    assert ai.TOOLS["claude"].resume == ("--continue",)
    assert ai.TOOLS["gemini"].resume == ("--resume", "latest")
    assert ai.TOOLS["codex"].resume == ("resume", "--last")
    assert ai.TOOLS["agy"].resume == ("--continue",)
    assert ai.TOOLS["agy"].name == "Antigravity"
    assert ai.TOOLS["agy"].install_url == "https://antigravity.google/docs/getting-started?tab=cli"
    assert all(tool.fresh == () for tool in ai.TOOLS.values())


ZSH = None if sys.platform == "win32" else shutil.which("zsh")


def fake_tool(path: Path, log: Path, exit_on_resume: int) -> Path:
    """A stand-in for the AI tool: records its folder and arguments, fails resuming if asked to."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f"printf '%s|%s\\n' \"$(pwd)\" \"$*\" >> '{log}'\n"
        f'if [ -n "$1" ]; then exit {exit_on_resume}; fi\n'
        "exit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def run_script(tmp_path: Path, folder: Path, tool: ai.AiTool, resume: bool, exit_on_resume: int) -> tuple[list, str]:
    log = tmp_path / "calls.log"
    program_path = fake_tool(tmp_path / "bin" / tool.key, log, exit_on_resume)
    script = tmp_path / "launch.command"
    script.write_text(ai.macos_script(folder, program_path, tool, resume, notice="No earlier session"),
                      encoding="utf-8")
    script.chmod(0o700)
    # -f: no rc files; the shebang's login shell is Terminal's business.
    result = subprocess.run([ZSH, "-f", str(script)], capture_output=True, text=True, timeout=30,
                            cwd=tmp_path, env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert not script.exists()  # it deleted itself
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return calls, result.stdout


def run_copied_command(tmp_path: Path, folder: Path, tool: ai.AiTool, resume: bool,
                       exit_on_resume: int) -> tuple[list, str]:
    log = tmp_path / "calls.log"
    program_path = fake_tool(tmp_path / "bin" / tool.key, log, exit_on_resume)
    command = ai.copy_command_text(folder, tool, resume)
    assert "\n" not in command
    # Simulate pasting at the prompt, with the AI executable already on the terminal's PATH.
    result = subprocess.run(
        [ZSH, "-fc", command], capture_output=True, text=True, timeout=30, cwd=tmp_path,
        env={"PATH": f"{program_path.parent}:/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return calls, result.stdout


@pytest.mark.skipif(ZSH is None, reason="needs zsh")
@pytest.mark.parametrize("run", [run_script, run_copied_command])
@pytest.mark.parametrize("name", [GUZ, QUOTED, HOSTILE])
def test_the_macos_launcher_runs_in_the_term_folder_whatever_its_name(name, tmp_path, run):
    folder = tmp_path / "University" / name
    folder.mkdir(parents=True)
    calls, out = run(tmp_path, folder, ai.TOOLS["claude"], resume=True, exit_on_resume=0)
    assert calls == [f"{folder.resolve()}|--continue"]
    assert not out
    assert not (tmp_path / "pwned").exists() and not (folder / "pwned").exists()


@pytest.mark.skipif(ZSH is None, reason="needs zsh")
@pytest.mark.parametrize("run", [run_script, run_copied_command])
@pytest.mark.parametrize("key", ai.AI_CLIS)
def test_a_resume_that_fails_at_once_starts_a_new_session(key, tmp_path, run):
    folder = tmp_path / "University" / GUZ
    folder.mkdir(parents=True)
    tool = ai.TOOLS[key]
    calls, out = run(tmp_path, folder, tool, resume=True, exit_on_resume=1)
    assert calls == [f"{folder.resolve()}|{' '.join(tool.resume)}", f"{folder.resolve()}|"]
    assert ("No earlier session" if run is run_script else ai.T_NO_SESSION) in out


@pytest.mark.skipif(ZSH is None, reason="needs zsh")
@pytest.mark.parametrize("run", [run_script, run_copied_command])
def test_resume_off_starts_a_new_session_only(tmp_path, run):
    folder = tmp_path / "University" / GUZ
    folder.mkdir(parents=True)
    calls, _ = run(tmp_path, folder, ai.TOOLS["codex"], resume=False, exit_on_resume=1)
    assert calls == [f"{folder.resolve()}|"]


@pytest.mark.skipif(ZSH is None, reason="needs zsh")
def test_a_missing_folder_starts_nothing(tmp_path):
    calls, _ = run_script(tmp_path, tmp_path / "gone", ai.TOOLS["claude"], resume=True, exit_on_resume=0)
    assert calls == []


# -- the Windows script ----------------------------------------------------------------------------

def test_powershell_strings_double_every_kind_of_single_quote():
    assert ai.ps_quote("Ali'nin") == "'Ali''nin'"
    assert ai.ps_quote("a\u2019b\u2018c\u201ad\u201be") == "'a\u2019\u2019b\u2018\u2018c\u201a\u201ad\u201b\u201be'"
    assert ai.ps_quote('$(x) `y` "z" %PATH%') == "'$(x) `y` \"z\" %PATH%'"  # nothing else is special inside


@pytest.mark.parametrize("key", ai.AI_CLIS)
def test_the_windows_script_goes_to_the_folder_and_falls_back_to_a_new_session(key):
    tool = ai.TOOLS[key]
    folder = PureWindowsPath(r"C:\Users\Öğrenci\University") / QUOTED
    program_path = PureWindowsPath(r"C:\Users\Öğrenci\AppData\Roaming\npm") / f"{key}.cmd"
    script = ai.windows_script(folder, program_path, tool, resume=True, notice="Yok")
    lines = script.splitlines()
    assert lines[0] == r"$env:Path = 'C:\Users\Öğrenci\AppData\Roaming\npm;' + $env:Path"
    assert lines[1] == r"Set-Location -LiteralPath 'C:\Users\Öğrenci\University\Ali''nin Dönemi' -ErrorAction Stop"
    resume_line = "& " + " ".join(f"'{part}'" for part in (str(program_path), *tool.resume))
    assert resume_line in lines
    assert f"if ($LASTEXITCODE -ne 0 -and ((Get-Date) - $bbsyncStart).TotalSeconds -lt {ai.FALLBACK_SECONDS}) {{" \
        in lines
    assert f"    & '{program_path}'" in lines
    fresh = ai.windows_script(folder, program_path, tool, resume=False)
    assert fresh.splitlines()[-1] == f"& '{program_path}'" and "LASTEXITCODE" not in fresh


POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


@pytest.mark.parametrize("terminal", WINDOWS_AI_TERMINALS)
def test_a_windows_terminal_never_parses_the_folder_or_the_program(terminal):
    script = ai.windows_script(PureWindowsPath(r"C:\U") / HOSTILE, PureWindowsPath(r"C:\npm\gemini.cmd"),
                               ai.TOOLS["gemini"], resume=True)
    wt = PureWindowsPath(r"C:\Apps\wt.exe")
    argv = ai.windows_commands(script, terminal, wt, r"C:\Windows")
    encoded = ai.encode_powershell(script)
    stays = [POWERSHELL, "-NoLogo", "-NoProfile", "-NoExit", "-EncodedCommand", encoded]
    assert argv == {
        "windows_terminal": [str(wt), "new-tab", *stays],
        "powershell": stays,
        "cmd": [r"C:\Windows\System32\cmd.exe", "/k", POWERSHELL, "-NoLogo", "-NoProfile", "-EncodedCommand",
                encoded],
    }[terminal]
    assert set(encoded) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    assert base64.b64decode(encoded).decode("utf-16-le") == script
    assert not any(HOSTILE in part or "gemini" in part for part in argv)


# -- launching -------------------------------------------------------------------------------------

def detector(**found) -> ai.Detector:
    return ai.Detector(lambda: {key: found.get(key) for key in ai.AI_CLIS})


def test_nothing_opens_without_a_tool_an_install_or_the_folder(tmp_path):
    config = make_config(tmp_path, {"_1_1": course(GUZ)})
    never = lambda *a, **k: pytest.fail("no terminal may open")  # noqa: E731
    result = ai.launch("", True, config, detector(), run=never, spawn=never)
    assert (result.ok, result.failure) == (False, ai.Failure.NO_AI)
    result = ai.launch("gemini", True, config, detector(claude=Path("/x/claude")), run=never, spawn=never)
    assert (result.failure, result.tool.name) == (ai.Failure.CLI_MISSING, "Gemini CLI")
    assert result.tool.install_url == "https://github.com/google-gemini/gemini-cli"
    result = ai.launch("claude", True, config, detector(claude=Path("/x/claude")), run=never, spawn=never)
    assert (result.failure, result.folder) == (ai.Failure.FOLDER_MISSING, config.root / GUZ)


@pytest.mark.skipif(sys.platform == "win32", reason="macOS paths and file modes")
def test_macos_opens_terminal_with_a_private_script_that_deletes_itself(tmp_path):
    config = make_config(tmp_path, {"_1_1": course(GUZ)})
    (config.root / GUZ).mkdir(parents=True)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        script = Path(argv[-1])
        assert stat.S_IMODE(script.stat().st_mode) == 0o700
        assert f"cd -- '{config.root / GUZ}'" in script.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = ai.launch("codex", True, config, detector(codex=Path("/x/codex")), platform="darwin", run=run)
    assert result.ok and result.folder == config.root / GUZ and result.tool.key == "codex"
    assert calls[0][:3] == ["/usr/bin/open", "-a", "Terminal"]
    assert Path(calls[0][3]).parent == config.data_dir / ai.LAUNCH_DIR


@pytest.mark.skipif(sys.platform == "win32", reason="macOS paths and file modes")
def test_macos_reports_a_terminal_that_did_not_open_and_cleans_up(tmp_path):
    config = make_config(tmp_path, {"_1_1": course(GUZ)})
    (config.root / GUZ).mkdir(parents=True)
    failed = lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "", "Unable to find application named 'Terminal'\n")  # noqa: E731,E501
    result = ai.launch("claude", True, config, detector(claude=Path("/x/claude")), platform="darwin", run=failed)
    assert (result.failure, result.error) == (ai.Failure.TERMINAL_FAILED, "Unable to find application named 'Terminal'")
    assert result.folder == config.root / GUZ  # the caller opens it in Finder instead
    assert list((config.data_dir / ai.LAUNCH_DIR).iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="macOS paths and file modes")
def test_old_scripts_terminal_never_ran_are_removed(tmp_path):
    folder = tmp_path / "data" / ai.LAUNCH_DIR
    folder.mkdir(parents=True)
    old, recent = folder / "bbsync-ai-old.command", folder / "bbsync-ai-recent.command"
    for path in (old, recent):
        path.write_text("", encoding="utf-8")
    os.utime(old, (0, 0))
    new = ai._write_script(tmp_path / "data", "echo\n", now=ai.STALE_SCRIPT_SECONDS + 10)
    assert not old.exists() and recent.exists() and new.exists()


class Spawner:
    def __init__(self, fail_first: int = 0):
        self.calls, self.fail_first = [], fail_first

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if len(self.calls) <= self.fail_first:
            raise FileNotFoundError(argv[0])
        return object()


def windows_launch(tmp_path, config, key, resume, terminal_app, spawn, chosen="", **found):
    env = windows_env(tmp_path, terminal_app, **found)
    terminals = ai.Detector(lambda: ai.detect_terminals("win32", env=env, home=tmp_path))
    return ai.launch(key, resume, config, detector(**{key: PureWindowsPath(r"C:\npm") / f"{key}.cmd"}),
                     platform="win32", env=env, spawn=spawn, terminal=chosen, terminals=terminals)


def programs(spawn: Spawner) -> list[str]:
    return [argv[0].replace("/", "\\").rsplit("\\", 1)[-1] for argv, _ in spawn.calls]


def term_config(tmp_path: Path) -> Config:
    config = make_config(tmp_path, {"_1_1": course(GUZ)})
    (config.root / GUZ).mkdir(parents=True)
    return config


def test_windows_opens_windows_terminal_in_the_term_folder(tmp_path):
    config = term_config(tmp_path)
    spawn = Spawner()
    result = windows_launch(tmp_path, config, "claude", True, True, spawn)
    assert result.ok and result.terminal.key == "windows_terminal"
    (argv, kwargs), = spawn.calls
    assert argv[0].endswith("wt.exe") and argv[1] == "new-tab" and argv[2].endswith("powershell.exe")
    assert kwargs["cwd"] == str(config.root / GUZ) and kwargs["creationflags"] == ai.DETACHED_PROCESS
    script = base64.b64decode(argv[-1]).decode("utf-16-le")
    assert f"Set-Location -LiteralPath '{config.root / GUZ}'" in script and "'--continue'" in script


def test_windows_without_windows_terminal_opens_a_powershell_console(tmp_path):
    spawn = Spawner()
    result = windows_launch(tmp_path, term_config(tmp_path), "gemini", False, False, spawn)
    assert result.ok and result.terminal.key == "powershell"
    (argv, kwargs), = spawn.calls
    assert programs(spawn) == ["powershell.exe"] and kwargs["creationflags"] == ai.CREATE_NEW_CONSOLE
    assert "LASTEXITCODE" not in base64.b64decode(argv[-1]).decode("utf-16-le")  # resume is off


@pytest.mark.parametrize("chosen, opened", [("powershell", "powershell.exe"), ("cmd", "cmd.exe")])
def test_windows_opens_the_chosen_console(tmp_path, chosen, opened):
    spawn = Spawner()
    result = windows_launch(tmp_path, term_config(tmp_path), "claude", True, True, spawn, chosen)
    assert result.ok and result.terminal.key == chosen
    assert programs(spawn) == [opened] and spawn.calls[0][1]["creationflags"] == ai.CREATE_NEW_CONSOLE


def test_windows_uses_its_own_terminal_when_the_chosen_one_is_gone(tmp_path):
    spawn = Spawner()
    result = windows_launch(tmp_path, term_config(tmp_path), "claude", True, False, spawn, "windows_terminal")
    assert result.ok and result.terminal.key == "powershell" and programs(spawn) == ["powershell.exe"]


def test_windows_falls_back_to_powershell_and_reports_when_nothing_starts(tmp_path):
    config = term_config(tmp_path)
    spawn = Spawner(fail_first=1)
    assert windows_launch(tmp_path / "a", config, "codex", True, True, spawn).ok
    assert programs(spawn) == ["wt.exe", "powershell.exe"]
    result = windows_launch(tmp_path / "b", config, "codex", True, True, Spawner(fail_first=2))
    assert result.failure == ai.Failure.TERMINAL_FAILED and "powershell.exe" in result.error
    spawn = Spawner(fail_first=1)  # a terminal the student chose is not swapped for another
    result = windows_launch(tmp_path / "c", config, "codex", True, True, spawn, "windows_terminal")
    assert result.failure == ai.Failure.TERMINAL_FAILED and programs(spawn) == ["wt.exe"]


@pytest.mark.skipif(sys.platform == "win32", reason="macOS paths and file modes")
@pytest.mark.parametrize("chosen, used", [("iterm2", "iterm2"), ("kitty", "kitty"), ("ghostty", "terminal"),
                                          ("cmd", "terminal"), ("", "terminal")])
def test_macos_opens_the_chosen_terminal_while_it_is_there(tmp_path, chosen, used):
    config = term_config(tmp_path)
    for app in ("iTerm.app", "kitty.app"):
        (tmp_path / "Applications" / app).mkdir(parents=True)
    terminals = ai.Detector(lambda: ai.detect_terminals("darwin", env={}, home=tmp_path,
                                                        app_dirs=("~/Applications",)))
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = ai.launch("claude", True, config, detector(claude=Path("/x/claude")), platform="darwin", run=run,
                       terminal=chosen, terminals=terminals)
    assert result.ok and result.terminal.key == used
    (argv, kwargs), = calls
    assert argv[0] == ("/usr/bin/osascript" if used == "iterm2" else "/usr/bin/open")
    assert kwargs["timeout"] == (ai.AUTOMATION_TIMEOUT if used == "iterm2" else ai.OPEN_TIMEOUT)
    if used == "kitty":
        assert argv[2] == str(tmp_path / "Applications" / "kitty.app") and str(config.root / GUZ) in argv


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths")
def test_launch_looks_for_the_tool_again_each_time(tmp_path):
    config = make_config(tmp_path, {"_1_1": course(GUZ)})
    seen = []
    tools = ai.Detector(lambda: seen.append(1) or {"claude": None, "gemini": None, "codex": None, "agy": None})
    ai.launch("claude", True, config, tools)
    ai.launch("claude", True, config, tools)
    assert len(seen) == 2
