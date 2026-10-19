import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest


def load_builder() -> ModuleType:
    script = Path(__file__).resolve().parents[2] / "scripts" / "build_package.py"
    spec = importlib.util.spec_from_file_location("build_package", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_find_modern_7zip_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = load_builder()
    monkeypatch.setattr(builder.shutil, "which", lambda command: "/usr/bin/7zz" if command == "7zz" else None)
    assert builder.find_7z_binary() == "/usr/bin/7zz"


@pytest.mark.parametrize("edition", ["cpu", "cuda", "dml", "mac"])
def test_package_freezes_isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, edition: str) -> None:
    builder = load_builder()
    monkeypatch.setattr(builder, "PROJECT_ROOT", tmp_path)
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
        commands.append(cmd)
        if "PyInstaller" in cmd:
            frozen = Path(cmd[cmd.index("--distpath") + 1]) / "main"
            (frozen / "_internal").mkdir(parents=True)
            (frozen / "main.exe").touch()

    monkeypatch.setattr(builder, "run_cmd", fake_run)
    package = builder.build_package(edition, skip_archive=True)

    assert (package / "main.exe").is_file()
    assert (package / "_internal").is_dir()
    assert not (package / "runtime").exists()
    assert not (package / "backend").exists()
    assert (package / "modules").is_dir()
    assert (package / "model_dir").is_dir()
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

    def fake_run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
        if "PyInstaller" in cmd:
            (Path(cmd[cmd.index("--distpath") + 1]) / "main").mkdir(parents=True)
        elif cmd[0] == "7z":
            assert cwd is not None
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
