#!/usr/bin/env python3
"""Integration checks against locally owned inputs; no game data is bundled."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest import mock


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", required=True)
    parser.add_argument("--original", required=True)
    parser.add_argument("--previous", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--assets", required=True, help="Pristine game folder")
    args = parser.parse_args()
    distribution = Path(args.distribution).resolve()
    original = Path(args.original).read_bytes()
    previous = Path(args.previous).read_bytes()
    info = json.loads((distribution / "patch.json").read_text())
    results = []
    asset_root = Path(args.assets)
    asset_data = {r["path"]:(asset_root/r["path"]).read_bytes() for r in info["assets"]}

    def invoke(path, *options, success=True):
        result = subprocess.run([sys.executable, str(distribution / "install.py"), str(path), *options],
                                text=True, capture_output=True)
        check((result.returncode == 0) == success,
              f"Unexpected return code {result.returncode}: {result.stdout} {result.stderr}")
        return result

    def output_matches(path):
        data = path.read_bytes()
        for r in info["assets"]:
            b=(path.parent/r["path"]).read_bytes()
            check(len(b)==r["output"]["size"] and hashlib.sha256(b).hexdigest()==r["output"]["sha256"], "Asset output mismatch: "+r["path"])
        return len(data) == info["output"]["size"] and hashlib.sha256(data).hexdigest() == info["output"]["sha256"]

    with tempfile.TemporaryDirectory(prefix="u7-installer-tests-") as root:
        root = Path(root)

        def game(name, executable):
            folder = root / name
            folder.mkdir()
            (folder / "U7.EXE").write_bytes(executable)
            for name, data in asset_data.items():
                path = folder/name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(data)
            (folder/"TACTIC.DIF").write_bytes(b"\x04")
            (folder / "GAMEDAT").mkdir()
            (folder / "GAMEDAT" / "saved-progress").write_bytes(b"new player save - retain exactly\x00\xff")
            (folder / "U7CONFIG").write_bytes(b"user configuration - retain exactly")
            return folder

        def preserve(folder):
            check((folder / "GAMEDAT" / "saved-progress").read_bytes() == b"new player save - retain exactly\x00\xff", "Save changed")
            check((folder/"TACTIC.DIF").read_bytes()==b"\x04", "Difficulty preference changed")
            check((folder / "U7CONFIG").read_bytes() == b"user configuration - retain exactly", "Configuration changed")

        clean = game("clean", original)
        names_before = sorted(str(p.relative_to(clean)) for p in clean.rglob("*"))
        invoke(clean, "--check")
        check(names_before == sorted(str(p.relative_to(clean)) for p in clean.rglob("*")), "Check wrote game files")
        check((clean / "U7.EXE").read_bytes() == original, "Check modified executable")
        results.append("pristine check: complete output verified; no game writes")
        invoke(clean)
        check(output_matches(clean / "U7.EXE"), "Clean install output mismatch")
        check((clean / "TACTICAL-PATCH" / "U7.ORI").read_bytes() == original, "Original backup mismatch")
        preserve(clean)
        results.append("pristine install: exact release hash; verified backup; saves/config retained")
        stamp = (clean / "U7.EXE").stat().st_mtime_ns
        invoke(clean / "U7.EXE")
        invoke(clean, "--check")
        check((clean / "U7.EXE").stat().st_mtime_ns == stamp, "Idempotent install rewrote executable")
        results.append("current version: idempotent install/check and direct executable path")
        invoke(clean, "--uninstall")
        check((clean / "U7.EXE").read_bytes() == original, "Uninstall did not restore original")
        for name,data in asset_data.items():
            check((clean/name).read_bytes()==data, "Uninstall failed: "+name)
        check((clean / "TACTICAL-PATCH" / "U7.ORI").read_bytes() == original, "Uninstall removed backup")
        preserve(clean)
        invoke(clean, "--uninstall")
        results.append("uninstall: exact original restored; backup/save/config retained; repeat safe")

        upgrade = game("upgrade-v1.1", previous)
        (upgrade / "TACTICAL").mkdir()
        (upgrade / "TACTICAL" / "U7.ORI").write_bytes(original)
        (upgrade / "TACTICAL" / "player-note.txt").write_text("retain old user note")
        invoke(upgrade, "--check")
        invoke(upgrade)
        check(output_matches(upgrade / "U7.EXE"), "v1.1 upgrade output mismatch")
        check((upgrade / "TACTICAL" / "U7.ORI").read_bytes() == original, "Old original backup changed")
        check((upgrade / "TACTICAL" / "player-note.txt").read_text() == "retain old user note", "User note changed")
        preserve(upgrade)
        results.append("v1.1 upgrade: existing local original recognized; old files and new progress retained")

        missing = game("v1.1-missing-original", previous)
        invoke(missing, success=False)
        check((missing / "U7.EXE").read_bytes() == previous, "Missing-original failure changed executable")
        check(not (missing / "TACTICAL-PATCH").exists(), "Missing-original failure wrote backup folder")
        original_path = root / "external-original"
        original_path.write_bytes(original)
        invoke(missing, "--original", str(original_path))
        check(output_matches(missing / "U7.EXE"), "Explicit original upgrade failed")
        results.append("v1.1 missing backup: refused without writes; explicit verified original succeeds")

        bad = game("unknown", original[:-1] + bytes([original[-1] ^ 1]))
        before = (bad / "U7.EXE").read_bytes()
        invoke(bad, success=False)
        invoke(bad, "--uninstall", success=False)
        check((bad / "U7.EXE").read_bytes() == before and not (bad / "TACTICAL-PATCH").exists(), "Unknown input changed")
        preserve(bad)
        results.append("unknown/modified executable: install/uninstall refused without writes")

        conflict = game("conflicting-backup", original)
        (conflict / "TACTICAL-PATCH").mkdir()
        (conflict / "TACTICAL-PATCH" / "U7.ORI").write_bytes(b"do not overwrite")
        invoke(conflict, "--check", success=False)
        invoke(conflict, success=False)
        check((conflict / "U7.EXE").read_bytes() == original, "Backup conflict changed executable")
        check((conflict / "TACTICAL-PATCH" / "U7.ORI").read_bytes() == b"do not overwrite", "Backup conflict overwritten")
        results.append("conflicting backup: check/install refused; both existing files retained")

        locked = game("installation-lock", original)
        (locked / "TACTICAL-PATCH").mkdir()
        (locked / "TACTICAL-PATCH" / "INSTALL.lock").write_text("12345\n")
        invoke(locked, success=False)
        check((locked / "U7.EXE").read_bytes() == original, "Lock failure changed executable")
        results.append("concurrent installer lock: refused before executable replacement")

        # Exercise the actual fallback even on this host's hard-link filesystem.
        spec = importlib.util.spec_from_file_location("tested_tactical_installer", distribution / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        fallback = game("no-hard-links", original)
        with mock.patch.object(installer.os, "link", side_effect=OSError("hard links unsupported")):
            with mock.patch("sys.stdout", new=io.StringIO()):
                installer.install(fallback)
        check(output_matches(fallback / "U7.EXE"), "Hard-link fallback installation mismatch")
        check((fallback / "TACTICAL-PATCH" / "U7.ORI").read_bytes() == original, "Fallback backup mismatch")
        results.append("FAT/exFAT backup fallback: exclusive creation, verified backup, exact installed hash")

        failed = game("replacement-failure", original)
        with mock.patch.object(installer.os, "replace", side_effect=OSError("simulated replacement failure")):
            try:
                installer.install(failed)
            except OSError:
                pass
            else:
                raise AssertionError("Expected replacement failure")
        check((failed / "U7.EXE").read_bytes() == original, "Failed replacement changed executable")
        check((failed / "TACTICAL-PATCH" / "U7.ORI").read_bytes() == original, "Failed replacement lost backup")
        check(not (failed / "TACTICAL-PATCH" / "INSTALL.lock").exists(), "Failed replacement left lock")
        results.append("replacement failure: original executable retained; verified backup and no stale lock")

        for name in asset_data:
            tampered=game("tampered-"+Path(name).name,original)
            path=tampered/name;before=path.read_bytes();path.write_bytes(before[:-1]+bytes([before[-1]^1]))
            invoke(tampered,success=False)
            check((tampered/"U7.EXE").read_bytes()==original and not (tampered/"TACTICAL-PATCH").exists(), "Asset rejection wrote files")
        results.append("all four changed resources: independent modification rejected before any write")

        partial=game("rollback",original)
        real_replace=installer.os.replace;commits=[0]
        def fail_fourth(source,target):
            if Path(target).name in {"U7.EXE","MAINMENU.EXE","USECODE","LINKDEP1","LINKDEP2"}:
                commits[0]+=1
                if commits[0]==4:raise OSError("fourth replacement fails")
            return real_replace(source,target)
        with mock.patch.object(installer.os,"replace",side_effect=fail_fourth):
            try:installer.install(partial)
            except OSError:pass
            else:raise AssertionError("Expected fourth commit failure")
        check((partial/"U7.EXE").read_bytes()==original,"Rollback U7 failed")
        for name,data in asset_data.items():check((partial/name).read_bytes()==data,"Rollback asset failed")
        results.append("multi-file failure: three committed replacements rolled back; originals and backups retained")

    report = {"version": info["version"], "output_sha256": info["output"]["sha256"],
              "status": "passed", "checks": results}
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
