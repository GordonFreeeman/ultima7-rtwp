#!/usr/bin/env python3
"""Build a shareable source/patch-object package; never package a game executable."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
V7 = {"version": "v7", "size": 713824,
      "sha256": "7e7d908a0885627f545fd6a6ef299d34e170bdb19bfc85e8db6d2d05b5f01349"}
V11 = {"version": "1.1", "size": 713824,
       "sha256": "0f203c9b0e63b11c5d3319247640285548fca333596c259706eee07c74a62786"}
MARKER = {"kind": "u7-tactical-patch-distribution", "format": 1}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_native(source):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("distribution_native_patcher", source / "native_patcher.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(args):
    source = Path(args.source).resolve()
    destination = Path(args.output).resolve()
    native = load_native(source)
    native.require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}", args.version) is not None,
                   "Version must be a short filename-safe label")
    protected = [source, HERE, Path(args.original).resolve(), Path(args.mainmenu).resolve(),
                 Path(args.usecode).resolve(), Path(args.usecode).resolve().parent/'LINKDEP1',
                 Path(args.usecode).resolve().parent/'LINKDEP2']
    protected.extend(Path(value).resolve() for value in (args.expected, args.previous) if value)
    native.require(not Path(args.output).is_symlink(), "Output must not be a symbolic link")
    native.require(all(p != destination and not p.is_relative_to(destination) for p in protected),
                   "Output must not contain or replace the source, build tool, or an input file")
    if destination.exists():
        marker = destination / "distribution-marker.json"
        native.require(destination.is_dir() and marker.is_file() and
                       json.loads(marker.read_text(encoding="utf-8")) == MARKER,
                       "Output already exists and is not a generated patch distribution; choose a new directory")
    archive = Path(args.archive).resolve() if args.archive else None
    if archive:
        native.require(archive.suffix.casefold() == ".zip", "Archive path must end in .zip")
        native.require(not archive.is_relative_to(destination), "Archive must be outside the distribution directory")
        native.require(not archive.is_relative_to(source) and archive not in protected,
                       "Archive must not replace a source or input file")
    original = Path(args.original).read_bytes()
    native.require(len(original) == native.BASELINE_SIZE and digest(original) == native.BASELINE_SHA256,
                   "Unsupported original executable")
    if args.previous:
        previous = Path(args.previous).read_bytes()
        native.require(any(len(previous)==x['size'] and digest(previous)==x['sha256'] for x in [V7,V11]),
                       "Previous-version verification failed")
    with tempfile.TemporaryDirectory(prefix="u7-share-build-") as temporary:
        temporary = Path(temporary)
        staged = temporary / "distribution"
        frozen_source = staged / "source"
        frozen_source.mkdir(parents=True)
        source_hashes = {}
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix in {".asm", ".inc", ".py"}:
                relative = path.relative_to(source)
                target = frozen_source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                source_hashes[relative.as_posix()] = digest(target.read_bytes())
        # Compile the very source tree that will be distributed, so an editor
        # changing the working source cannot separate objects from their source.
        native = load_native(frozen_source)
        native.require(len(original) == native.BASELINE_SIZE and digest(original) == native.BASELINE_SHA256,
                       "Unsupported original executable in frozen build source")
        prepared = native.Executable(original)
        prepared.expand()
        object_paths = []
        object_records = []
        for path in sorted(frozen_source.glob("*.asm")):
            target = temporary / (path.stem + ".o")
            subprocess.run([str(Path(shutil.which(args.nasm) or args.nasm).resolve()), str(path), "-o", str(target)],
                           cwd=frozen_source, check=True)
            data = target.read_bytes()
            description, length, blocks = native.read_patch(data)
            native.require(length == len(prepared.data), "Unexpected patch target length")
            native.require(blocks, "Empty patch object")
            object_paths.append(target)
            object_records.append({"source": path.name, "description": description,
                                   "size": len(data), "sha256": digest(data),
                                   "zlib_base64": base64.b64encode(zlib.compress(data, 9)).decode("ascii")})
        native.require(object_paths, "No assembly sources found")
        blocks = prepared.patch(object_paths)
        output = bytes(prepared.data)
        if args.expected:
            native.require(output == Path(args.expected).read_bytes(),
                           "Assembled source does not reproduce the expected final executable")
        native.Executable(output)
        info = {"format": "u7-native-tactical-objects-v1", "version": args.version,
                "original": {"size": len(original), "sha256": digest(original),
                             "description": "English Ultima VII: The Black Gate 3.4 / Forge of Virtue"},
                "output": {"size": len(output), "sha256": digest(output)},
                "accepted_previous": [V7,V11], "source_sha256": source_hashes,
                "objects": object_records}
        asset_spec = importlib.util.spec_from_file_location('distribution_assets',frozen_source/'asset_patcher.py')
        assets = importlib.util.module_from_spec(asset_spec)
        asset_spec.loader.exec_module(assets)
        menu_object = temporary/'menu.bin'
        subprocess.run([str(Path(shutil.which(args.nasm) or args.nasm).resolve()),
                        str(frozen_source/'menu/menu.asm'),'-o',str(menu_object)],check=True)
        menu_input = Path(args.mainmenu).read_bytes()
        usecode_input = Path(args.usecode).read_bytes()
        link_inputs = [(Path(args.usecode).parent/name).read_bytes() for name in ('LINKDEP1','LINKDEP2')]
        native.require(tuple(link_inputs)==assets.link_dependencies(usecode_input), 'Unsupported native dependency tables')
        usecode_output = assets.patch_usecode(usecode_input)
        link_outputs = assets.link_dependencies(usecode_output)
        menu_payload = menu_object.read_bytes()
        info['menu_payload'] = {'size':len(menu_payload),'sha256':digest(menu_payload),
                                'zlib_base64':base64.b64encode(zlib.compress(menu_payload,9)).decode('ascii')}
        info['assets'] = []
        for name,backup,before,after in [
            ('MAINMENU.EXE','MAINMENU.ORI',menu_input,assets.patch_menu(menu_input,menu_payload)),
            ('STATIC/USECODE','USECODE.ORI',usecode_input,usecode_output),
            ('STATIC/LINKDEP1','LINKDEP1.ORI',link_inputs[0],link_outputs[0]),
            ('STATIC/LINKDEP2','LINKDEP2.ORI',link_inputs[1],link_outputs[1])]:
            info['assets'].append({'path':name,'backup':backup,
                'original':{'size':len(before),'sha256':digest(before)},
                'output':{'size':len(after),'sha256':digest(after)}})
        (staged / "patch.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        (staged / "distribution-marker.json").write_text(json.dumps(MARKER, indent=2) + "\n", encoding="utf-8")
        for name in ("install.py", "build_distribution.py", "README.md", "HANDOVER.md", "LICENSE-UPSTREAM.txt", "ATTRIBUTION.md"):
            shutil.copy2(HERE / name, staged / name)
        (staged/'tests').mkdir()
        for name in ('test_native.py','test_assets.py','test_install.py'):
            shutil.copy2(HERE/'tests'/name,staged/'tests'/name)
        # Only these reviewed public reports are optional. Private tests,
        # diagnostics, input executables and evidence are never swept in.
        for name in ("VALIDATION.txt", "VALIDATION.json", "REVERSE_ENGINEERING.txt"):
            path = HERE / name
            if path.is_file():
                shutil.copy2(path, staged / name)
        audit = {"version": args.version, "original": info["original"], "output": info["output"],
                 "assets": info['assets'],
                 "patch_blocks": blocks, "source_sha256": source_hashes,
                 "distribution_contents": "source, replacement patch objects, installer, documentation, license notice",
                 "not_included": ["original or patched executable", "original overlay code", "game assets", "save files", "configuration", "gameplay screenshots"]}
        (staged / "BUILD.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        native.require(not any(p.suffix.casefold() in {".exe", ".com", ".dat", ".sav", ".png", ".bmp"}
                               for p in staged.rglob("*") if p.is_file()), "Game content appeared in the distribution")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(staged, destination)
    if archive:
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive_temporary = archive.with_name(archive.name + ".tmp")
        with zipfile.ZipFile(archive_temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for path in sorted(destination.rglob("*")):
                if path.is_file():
                    bundle.write(path, f"Ultima7-Tactical-Patch-{args.version}/{path.relative_to(destination).as_posix()}")
        with zipfile.ZipFile(archive_temporary) as bundle:
            native.require(bundle.testzip() is None, "ZIP integrity verification failed")
            expected_members = {f"Ultima7-Tactical-Patch-{args.version}/{p.relative_to(destination).as_posix()}": p
                                for p in destination.rglob("*") if p.is_file()}
            native.require(set(bundle.namelist()) == set(expected_members), "ZIP member verification failed")
            for name, path in expected_members.items():
                native.require(digest(bundle.read(name)) == digest(path.read_bytes()),
                               f"ZIP content verification failed: {name}")
        archive_temporary.replace(archive)
    print(json.dumps({"version": args.version, "output_sha256": info["output"]["sha256"],
                      "compiled_patch_bytes": sum(x["size"] for x in object_records),
                      "source_files": len(source_hashes), "distribution": str(destination)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, help="Locally owned pristine supported U7.EXE")
    parser.add_argument("--expected", help="Locally built final U7.EXE to reproduce exactly")
    parser.add_argument("--mainmenu", required=True, help="Locally owned pristine MAINMENU.EXE")
    parser.add_argument("--usecode", required=True, help="Locally owned pristine STATIC/USECODE")
    parser.add_argument("--previous", help="Local v7 U7.EXE to verify the upgrade identity")
    parser.add_argument("--source", default=str(HERE / "source" if (HERE / "source").is_dir() else HERE.parent / "native-mod"))
    parser.add_argument("--nasm", default=shutil.which("nasm") or "nasm")
    parser.add_argument("--version", default="1.2")
    parser.add_argument("--output", default=str(HERE / "release"))
    parser.add_argument("--archive", help="Optional ZIP path outside the release directory")
    build(parser.parse_args())
