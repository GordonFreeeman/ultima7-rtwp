#!/usr/bin/env python3
"""Install a hash-guarded native Ultima VII tactical patch using local game data."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parent
BACKUP_DIR = "TACTICAL-PATCH"
BACKUP_NAME = "U7.ORI"


class InstallError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise InstallError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def matches(data, identity):
    return len(data) == identity["size"] and sha(data) == identity["sha256"]


def load_distribution():
    try:
        info = json.loads((ROOT / "patch.json").read_text(encoding="utf-8"))
        require(info["format"] == "u7-native-tactical-objects-v1",
                "This patch package has an unsupported format.")
        for name, digest in info["source_sha256"].items():
            relative = Path(name)
            require(not relative.is_absolute() and ".." not in relative.parts,
                    "Invalid source path in this patch package.")
            require(sha((ROOT / "source" / relative).read_bytes()) == digest,
                    "A source file in this patch package changed. Re-extract the complete package.")
        path = ROOT / "source" / "native_patcher.py"
        spec = importlib.util.spec_from_file_location("tactical_native_patcher", path)
        require(spec is not None and spec.loader is not None, "Cannot load the native patcher.")
        native = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = native
        # Keep the distribution directory unchanged during checks and installs.
        sys.dont_write_bytecode = True
        spec.loader.exec_module(native)
        objects = []
        for record in info["objects"]:
            packed = base64.b64decode(record["zlib_base64"], validate=True)
            dec = zlib.decompressobj()
            data = dec.decompress(packed, 2_000_001)
            require(len(data) <= 2_000_000 and dec.eof and not dec.unused_data,
                    "Invalid compressed patch object.")
            require(len(data) == record["size"] and sha(data) == record["sha256"],
                    "A compiled patch object is damaged. Re-extract the complete package.")
            native.read_patch(data)
            objects.append(data)
        require(objects, "This patch package contains no compiled patch objects.")
        return info, native, objects
    except InstallError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise InstallError("Cannot read this patch package. Re-extract the complete package.") from error


def locate_executable(target):
    supplied = Path(target).expanduser()
    if supplied.is_dir():
        candidates = [p for p in supplied.iterdir()
                      if p.is_file() and p.name.casefold() == "u7.exe"]
        require(len(candidates) == 1,
                "Choose the game folder containing U7.EXE, or supply the full path to U7.EXE.")
        supplied = candidates[0]
    require(supplied.is_file(), "Cannot find U7.EXE at that path.")
    require(not supplied.is_symlink(), "Use the real U7.EXE file rather than a symbolic link.")
    return supplied.resolve()


def read_original(exe_path, current, info, explicit=None):
    if matches(current, info["original"]):
        original = current
        if explicit is not None:
            require(matches(Path(explicit).expanduser().read_bytes(), info["original"]),
                    "The supplied original file is not the supported pristine U7.EXE.")
        return original
    known = next((x for x in info["accepted_previous"] if matches(current, x)), None)
    require(known is not None,
            "This U7.EXE is an unsupported version or has other changes. No game files were changed.")
    candidates = ([Path(explicit).expanduser()] if explicit is not None else [
        exe_path.parent / BACKUP_DIR / BACKUP_NAME,
        exe_path.parent / "TACTICAL" / "U7.ORI",
    ])
    for candidate in candidates:
        if candidate.is_file():
            data = candidate.read_bytes()
            if matches(data, info["original"]):
                return data
    raise InstallError(
        "The previous tactical version is supported, but its verified original executable is missing. "
        "Keep TACTICAL/U7.ORI from that installation, or add --original followed by the path to "
        "your supported pristine U7.EXE. No game files were changed.")


def prepare_output(original, info, native, objects):
    require(matches(original, info["original"]), "The original executable did not pass verification.")
    exe = native.Executable(original)
    exe.expand()
    with tempfile.TemporaryDirectory(prefix="u7-tactical-objects-") as temporary:
        paths = []
        for index, data in enumerate(objects):
            path = Path(temporary) / f"{index:04d}.o"
            path.write_bytes(data)
            paths.append(path)
        exe.patch(paths)
    output = bytes(exe.data)
    require(matches(output, info["output"]),
            "The prepared executable did not match this release. No game files were changed.")
    # Reparse loader metadata before writing anything to the game folder.
    native.Executable(output)
    return output


def verified_backup(exe_path, info, explicit=None):
    candidates = ([Path(explicit).expanduser()] if explicit is not None else [
        exe_path.parent / BACKUP_DIR / BACKUP_NAME,
        exe_path.parent / "TACTICAL" / "U7.ORI",
    ])
    for path in candidates:
        if path.is_file():
            data = path.read_bytes()
            if matches(data, info["original"]):
                return data
    raise InstallError(
        "Cannot restore the original: a verified U7.ORI backup is missing. Add --original followed "
        "by the path to your supported pristine U7.EXE. No game files were changed.")


def store_backup(path, original):
    if path.exists():
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == original,
                "The backup path already contains a different file. It was left untouched; "
                "no game executable was changed.")
        return
    handle, temporary = tempfile.mkstemp(prefix=".u7-original-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link creates the destination atomically and never replaces an
        # existing backup. The temporary and backup paths share a filesystem.
        try:
            os.link(temporary, path)
        except FileExistsError:
            require(path.is_file() and not path.is_symlink() and path.read_bytes() == original,
                    "Another file appeared at the backup path. No game executable was changed.")
        except OSError:
            # FAT/exFAT and some mounted folders do not support hard links.
            # Exclusive creation never overwrites an existing backup. Finish
            # and verify this backup before the executable can be replaced.
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                require(path.is_file() and not path.is_symlink() and path.read_bytes() == original,
                        "Another file appeared at the backup path. No game executable was changed.")
            else:
                identity = os.fstat(descriptor)
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(original)
                        stream.flush()
                        os.fsync(stream.fileno())
                    require(path.read_bytes() == original, "Original backup verification failed.")
                except BaseException:
                    # Remove our incomplete file only if nobody replaced it.
                    if path.exists():
                        now = path.stat(follow_symlinks=False)
                        if (now.st_dev, now.st_ino) == (identity.st_dev, identity.st_ino):
                            path.unlink()
                    raise
    finally:
        Path(temporary).unlink(missing_ok=True)


def replace_executable(exe_path, expected_before, output):
    handle, temporary = tempfile.mkstemp(prefix=".u7-tactical-", dir=exe_path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        require(Path(temporary).read_bytes() == output, "Temporary output verification failed.")
        shutil.copystat(exe_path, temporary)
        require(exe_path.read_bytes() == expected_before,
                "U7.EXE changed while the installer was running. It was left untouched.")
        os.replace(temporary, exe_path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install(target=".", *, check=False, uninstall=False, original_path=None):
    info, native, objects = load_distribution()
    exe_path = locate_executable(target)
    current = exe_path.read_bytes()
    if uninstall:
        if matches(current, info["original"]):
            print("The supported original executable is already installed. Nothing changed.")
            return 0
        require(matches(current, info["output"]) or
                any(matches(current, x) for x in info["accepted_previous"]),
                "This U7.EXE is not a supported tactical version. No game files were changed.")
        replacement = verified_backup(exe_path, info, original_path)
    else:
        if matches(current, info["output"]):
            print(f"Tactical {info['version']} is already installed. Nothing changed.")
            return 0
        original = read_original(exe_path, current, info, original_path)
        replacement = prepare_output(original, info, native, objects)
        backup_dir = exe_path.parent / BACKUP_DIR
        require(not backup_dir.is_symlink(), "Use a real backup folder rather than a symbolic link.")
        require(not backup_dir.exists() or backup_dir.is_dir(), "The backup folder path is already a file.")
        backup_path = backup_dir / BACKUP_NAME
        if backup_path.exists() or backup_path.is_symlink():
            require(backup_path.is_file() and not backup_path.is_symlink() and backup_path.read_bytes() == original,
                    "The backup path already contains a different file. It was left untouched; "
                    "no game executable was changed.")
        if check:
            print(f"Ready to install Tactical {info['version']}. The game executable and patch passed verification.")
            print("No game files were changed.")
            return 0
    backup_dir = exe_path.parent / BACKUP_DIR
    require(not backup_dir.is_symlink(), "Use a real backup folder rather than a symbolic link.")
    backup_dir.mkdir(exist_ok=True)
    lock = backup_dir / "INSTALL.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise InstallError(
            "Another installation may be running. Close it before trying again. If a previous run "
            "was interrupted, remove TACTICAL-PATCH/INSTALL.lock after checking no installer is running.") from error
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(str(os.getpid()) + "\n")
        # All mutations happen after the input and complete output are verified.
        require(exe_path.read_bytes() == current, "U7.EXE changed. No executable was replaced.")
        if not uninstall:
            store_backup(backup_dir / BACKUP_NAME, original)
        replace_executable(exe_path, current, replacement)
    finally:
        lock.unlink(missing_ok=True)
    if uninstall:
        print("Restored the verified original U7.EXE. Saves, configuration, and backups were retained.")
    else:
        print(f"Installed Tactical {info['version']}. Start the game through your usual ULTIMA7.COM launcher.")
        print(f"Original executable backup: {BACKUP_DIR}/{BACKUP_NAME}. Saves and configuration were retained.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", nargs="?", default=".",
                        help="Game folder or U7.EXE path; defaults to the current folder")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Verify a complete installation without changing the game")
    action.add_argument("--uninstall", action="store_true", help="Restore a verified pristine backup")
    parser.add_argument("--original", help="Path to your supported pristine U7.EXE, if a local backup is unavailable")
    arguments = parser.parse_args()
    try:
        return install(arguments.game, check=arguments.check, uninstall=arguments.uninstall,
                       original_path=arguments.original)
    except (InstallError, OSError, ValueError) as error:
        print(f"Cannot complete the operation: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
