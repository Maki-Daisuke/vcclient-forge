import importlib.util
import json
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest


def load_builder(script_name: str = "build_package") -> ModuleType:
    script = Path(__file__).resolve().parents[2] / "scripts" / f"{script_name}.py"
    spec = importlib.util.spec_from_file_location(script_name, script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_artifacts(builder: ModuleType) -> Path:
    root = builder.PROJECT_ROOT
    frozen = builder.get_build_dir("cpu", "3.14") / "dist" / "main"
    executable = "main.exe" if builder.platform.system() == "Windows" else "main"
    for name in (executable, "_internal/runtime.dll"):
        destination = frozen / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"backend")
    manifest = builder.get_build_dir("cpu", "3.14") / "backend-manifest.json"
    manifest.write_text(json.dumps({executable: 7, "_internal/runtime.dll": 7}), encoding="utf-8")
    for name in ("index.html", "index.js", "945.index.js", "assets/image.png"):
        for directory in ("web_front", "frontend/dist"):
            destination = root / directory / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"frontend")
    for name in ("start.bat", "start.sh", "README.md", "LICENSE"):
        (root / name).write_text("asset", encoding="utf-8")
    if builder.platform.system() == "Windows":
        desktop = root / "src-tauri/target/release/vcclient-forge.exe"
        desktop.parent.mkdir(parents=True)
        desktop.write_bytes(b"desktop")
    return frozen


@pytest.mark.parametrize("version, expected", [("v9.8.7-forge.1", "9.8.7-forge.1"), ("9.8.7", "9.8.7")])
def test_package_version_comes_from_manifest(monkeypatch: pytest.MonkeyPatch, version: str, expected: str) -> None:
    read_manifest = Mock(return_value=json.dumps({"version": version}))
    monkeypatch.setattr(Path, "read_text", read_manifest)
    builder = load_builder()
    assert builder.VERSION == expected
    read_manifest.assert_called_once_with(encoding="utf-8")


def test_find_modern_7zip_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = load_builder()
    monkeypatch.setattr(builder.shutil, "which", lambda command: "/usr/bin/7zz" if command == "7zz" else None)
    assert builder.find_7z_binary() == "/usr/bin/7zz"


@pytest.mark.parametrize("edition", ["cpu", "cuda", "dml", "mac"])
def test_backend_freezes_isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, edition: str) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    freezer = load_builder("build_backend")
    builder = load_builder()
    monkeypatch.setattr(freezer, "package_tools", builder)
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(builder.platform, "system", lambda: "Windows")
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
        commands.append(cmd)
        if "PyInstaller" in cmd:
            frozen = Path(cmd[cmd.index("--distpath") + 1]) / "main"
            (frozen / "_internal").mkdir(parents=True)
            (frozen / "_internal/runtime.dll").write_bytes(b"runtime")
            (frozen / "main.exe").write_bytes(b"backend")

    monkeypatch.setattr(builder, "run_cmd", fake_run)
    package = freezer.freeze_backend(edition)

    assert (package / "main.exe").is_file()
    assert (package / "_internal").is_dir()
    assert not (package / "runtime").exists()
    assert not (package / "backend").exists()
    manifest = builder.get_build_dir(edition, "3.14") / "backend-manifest.json"
    assert json.loads(manifest.read_text(encoding="utf-8")) == {"_internal/runtime.dll": 7, "main.exe": 7}
    assert "--locked" in commands[1]
    assert commands[1][commands[1].index("--group") + 1] == "build"
    freeze = next(cmd for cmd in commands if "PyInstaller" in cmd)
    assert "--onedir" in freeze
    assert not Path(freeze[0]).is_relative_to(package)
    assert str(tmp_path / "backend" / "vcclient" / "version.txt") + ":vcclient" in freeze
    assert "vcclient.server.vcserver_socketio" in freeze
    assert ("nvidia.cudnn" in freeze) == (edition == "cuda")


@pytest.mark.parametrize("existing_artifact", ["directory", "archive"])
def test_existing_package_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing_artifact: str
) -> None:
    builder = load_builder()
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    package = tmp_path / "dist" / f"vcclient_{builder.get_platform_tag()}_cpu_v{builder.VERSION}"
    package.parent.mkdir(parents=True)
    if existing_artifact == "directory":
        package.mkdir()
    else:
        package.with_suffix(package.suffix + ".7z").touch()
    with pytest.raises(FileExistsError, match="choose a new --output-dir"):
        builder.build_package("cpu", skip_archive=True)


@pytest.mark.parametrize("archive_limit, succeeds", [(2, True), (1, False)])
def test_archive_size_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, archive_limit: int, succeeds: bool) -> None:
    builder = load_builder()
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(builder, "MAX_ARCHIVE_BYTES", archive_limit)
    monkeypatch.setattr(builder, "find_7z_binary", lambda: "7z")
    prepare_artifacts(builder)

    def fake_run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
        assert cmd[0] == "7z"
        assert cwd is not None
        expected_name = f"vcclient_{builder.get_platform_tag()}_cpu_v{builder.VERSION}"
        assert cmd[-2] == f"{expected_name}.7z"
        assert cmd[-1] == expected_name
        (cwd / cmd[-2]).write_bytes(b"x")

    monkeypatch.setattr(builder, "run_cmd", fake_run)
    if succeeds:
        assert builder.build_package("cpu").suffix == ".7z"
    else:
        with pytest.raises(RuntimeError, match="smaller than 2 GiB"):
            builder.build_package("cpu")


def test_frozen_frontend_is_next_to_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vcclient.server import server_const

    monkeypatch.setattr(server_const.sys, "frozen", True, raising=False)
    monkeypatch.setattr(server_const.sys, "executable", str(tmp_path / "relocated" / "main.exe"))
    assert server_const.get_frontend_path() == tmp_path / "relocated" / "frontend" / "dist"


def test_desktop_package_keeps_complete_backend_next_to_tauri(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    builder = load_builder()
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(builder.platform, "system", lambda: "Windows")
    frozen = prepare_artifacts(builder)
    commands = Mock(side_effect=AssertionError("Packaging must not build anything"))
    monkeypatch.setattr(builder, "run_cmd", commands)
    package = builder.build_package("cpu", skip_archive=True)
    assert package.name == f"vcclient_{builder.get_platform_tag()}_cpu_v{builder.VERSION}"
    assert (package / "vcclient-forge.exe").read_bytes() == b"desktop"
    assert (package / "main.exe").read_bytes() == b"backend"
    assert (package / "_internal").is_dir()
    assert (package / "frontend/dist/945.index.js").is_file()
    assert (package / "modules").is_dir()
    assert (package / "model_dir").is_dir()
    assert (frozen / "main.exe").is_file()
    commands.assert_not_called()
    second = builder.build_package("cpu", output_dir=tmp_path / "another-output", skip_archive=True)
    assert (second / "main.exe").is_file()


@pytest.mark.parametrize("system", ["Linux", "Darwin"])
def test_non_windows_package_retains_backend_only_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, system: str
) -> None:
    builder = load_builder()
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(builder.platform, "system", lambda: system)
    prepare_artifacts(builder)
    monkeypatch.setattr(builder, "run_cmd", Mock(side_effect=AssertionError("Must not build")))
    package = builder.build_package("cpu", skip_archive=True)
    assert package.name == f"vcclient_{builder.get_platform_tag()}_cpu_v{builder.VERSION}"
    assert (package / "main").is_file()
    assert not (package / "vcclient-forge.exe").exists()


@pytest.mark.parametrize(
    "missing_path",
    [
        "src-tauri/target/release/vcclient-forge.exe",
        "frontend/dist/index.html",
        "frontend/dist/index.js",
        "frontend/dist/945.index.js",
        "frontend/dist/assets/image.png",
        "start.bat",
        "LICENSE",
        "build/packaging/{platform}_cpu_3.14/backend-manifest.json",
        "build/packaging/{platform}_cpu_3.14/dist/main/main.exe",
        "build/packaging/{platform}_cpu_3.14/dist/main/_internal/runtime.dll",
    ],
)
def test_missing_artifact_fails_before_any_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_path: str
) -> None:
    builder = load_builder()
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(builder.platform, "system", lambda: "Windows")
    prepare_artifacts(builder)
    (tmp_path / missing_path.format(platform=builder.get_platform_tag())).unlink()
    commands = Mock()
    monkeypatch.setattr(builder, "run_cmd", commands)
    with pytest.raises(FileNotFoundError, match="Run npm run build"):
        builder.build_package("cpu")
    commands.assert_not_called()
    assert not (tmp_path / "dist").exists()


def test_package_rejects_truncated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    builder = load_builder()
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    frozen = prepare_artifacts(builder)
    (frozen / "_internal/runtime.dll").write_bytes(b"broken")
    with pytest.raises(FileNotFoundError, match="runtime.dll"):
        builder.build_package("cpu", skip_archive=True)


def test_backend_cli_only_syncs_and_freezes_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    freezer = load_builder("build_backend")
    commands = Mock()
    freeze = Mock()
    monkeypatch.setattr(freezer.package_tools, "run_cmd", commands)
    monkeypatch.setattr(freezer, "freeze_backend", freeze)
    monkeypatch.setattr("sys.argv", ["build_backend.py", "--edition", "cuda", "--python-version", "3.14"])
    freezer.main()
    commands.assert_called_once_with(
        ["uv", "sync", "--project", "backend", "--extra", "cuda"], cwd=freezer.package_tools.PROJECT_ROOT
    )
    freeze.assert_called_once_with("cuda", "3.14")


def test_npm_tasks_separate_build_from_packaging() -> None:
    root = Path(__file__).resolve().parents[2]
    tasks = json.loads((root / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert tasks["build"] == "node scripts/build.js"
    assert tasks["build:backend"].endswith("scripts/build_backend.py")
    assert tasks["package"].endswith("scripts/build_package.py")
    assert tasks["build:desktop"] == "tauri build --no-bundle -- --locked"
    assert not hasattr(load_builder(), "build_application")
    assert not hasattr(load_builder(), "build_backend")
    assert "--no-project" in tasks["package"]
    assert "build:package" not in tasks
    assert "build:desktop:package" not in tasks
    for edition in ("cpu", "cuda", "dml", "mac"):
        assert f"build:{edition}" not in tasks


@pytest.mark.parametrize("action", ["build", "build-backend"])
def test_package_cli_rejects_build_actions(monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    builder = load_builder()
    package = Mock()
    monkeypatch.setattr(builder, "build_package", package)
    monkeypatch.setattr("sys.argv", ["build_package.py", action])
    with pytest.raises(SystemExit) as error:
        builder.main()
    assert error.value.code == 2
    package.assert_not_called()


def test_failed_rebuild_invalidates_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    freezer = load_builder("build_backend")
    builder = load_builder()
    monkeypatch.setattr(freezer, "package_tools", builder)
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    prepare_artifacts(builder)
    monkeypatch.setattr(builder, "run_cmd", Mock(side_effect=RuntimeError("build failed")))
    with pytest.raises(RuntimeError, match="build failed"):
        freezer.freeze_backend("cpu")
    assert not (builder.get_build_dir("cpu", "3.14") / "backend-manifest.json").exists()


@pytest.mark.parametrize(
    "frozen, arguments, expected",
    [
        (True, ["main.exe"], ["server"]),
        (True, ["main.exe", "--", "--help"], None),
        (False, ["main.py"], None),
    ],
)
def test_only_frozen_no_argument_start_defaults_to_server(
    monkeypatch: pytest.MonkeyPatch, frozen: bool, arguments: list[str], expected: list[str] | None
) -> None:
    import main as entrypoint

    fire = Mock()
    monkeypatch.setattr(entrypoint.fire, "Fire", fire)
    monkeypatch.setattr(entrypoint.mp, "freeze_support", Mock())
    monkeypatch.setattr(entrypoint.sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(entrypoint.sys, "argv", arguments)

    entrypoint.main()

    fire.assert_called_once()
    assert fire.call_args.kwargs["command"] == expected
