"""Build the opt-in LU-stage extension into an ignored caller-selected folder.

Example (from the repository root):
    source .venv/bin/activate_myfenics_native.sh && \
      python scripts/build_petsc_lu_stage_bridge.py \
        --output-dir results/petsc_lu_stage_bridge/<abi-record>

This script never installs the extension and is never invoked by imports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import petsc4py
from petsc4py import PETSc
from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

ROOT = Path(__file__).resolve().parents[1]
BUILD_RECORD: dict[str, object] = {}


def _extension(output_dir: Path) -> Extension:
    if os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV") != "1":
        raise SystemExit("native complex activation marker is absent")
    # Keep the lexical venv path: resolving its python symlink would point at
    # the system interpreter and lose the activated project identity.
    if Path(os.path.abspath(sys.executable)).parent != ROOT / ".venv/bin":
        raise SystemExit(
            "builder must use the repository .venv interpreter from native activation"
        )
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise SystemExit(
            f"builder requires complex128 PETSc, got {np.dtype(PETSc.ScalarType)}"
        )
    petsc_dir_value = os.environ.get("PETSC_DIR")
    if not petsc_dir_value:
        raise SystemExit("PETSC_DIR is unset after native activation")
    petsc_dir = Path(petsc_dir_value).resolve()
    if "complex" not in str(petsc_dir):
        raise SystemExit(f"PETSC_DIR is not the expected complex ABI: {petsc_dir}")

    pkg_env = os.environ.copy()
    pkg_env["PKG_CONFIG_PATH"] = str(petsc_dir / "lib/pkgconfig")
    pc_dir = Path(
        subprocess.check_output(
            ["pkg-config", "--variable=pcfiledir", "PETSc"],
            text=True,
            env=pkg_env,
        ).strip()
    ).resolve()
    expected_pc_dir = (petsc_dir / "lib/pkgconfig").resolve()
    if pc_dir != expected_pc_dir:
        raise SystemExit(
            f"pkg-config selected PETSc.pc at {pc_dir}, expected {expected_pc_dir}"
        )
    pc_compiler = subprocess.check_output(
        ["pkg-config", "--variable=ccompiler", "PETSc"],
        text=True,
        env=pkg_env,
    ).strip()
    compiler_tokens = shlex.split(pc_compiler)
    if len(compiler_tokens) != 1:
        raise SystemExit(
            f"PETSc.pc ccompiler must name one executable, got {pc_compiler!r}"
        )
    compiler_lookup = shutil.which(compiler_tokens[0])
    if compiler_lookup is None:
        raise SystemExit(
            f"PETSc.pc ccompiler is unavailable in the activated PATH: {pc_compiler}"
        )
    # OpenMPI selects its wrapper configuration from argv[0].  Keep the
    # lexical `mpicc` name instead of resolving its symlink to opal_wrapper.
    compiler_path = str(Path(compiler_lookup).absolute())
    compiler_target = str(Path(compiler_path).resolve())
    compiler_show = subprocess.check_output(
        [compiler_path, "-show"], text=True, env=pkg_env
    ).strip()
    compiler_version = subprocess.check_output(
        [compiler_path, "--version"], text=True, env=pkg_env
    ).splitlines()[0]
    tokens = shlex.split(
        subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "PETSc"],
            text=True,
            env=pkg_env,
        )
    )
    if "-lpetsc_complex" not in tokens or "-lpetsc_real" in tokens:
        raise SystemExit(f"pkg-config selected an unexpected PETSc ABI: {tokens!r}")
    include_tokens = [
        token[2:]
        for token in tokens
        if token.startswith("-I") and token != "-I"
    ]
    library_tokens = [
        token[2:]
        for token in tokens
        if token.startswith("-L") and token != "-L"
    ]
    if str(petsc_dir / "include") not in include_tokens:
        raise SystemExit("current PETSc.pc cflags omit the activated PETSc headers")
    if str(petsc_dir / "lib") not in library_tokens:
        raise SystemExit("current PETSc.pc libs omit the activated PETSc library")
    BUILD_RECORD.update(
        {
            "petsc_dir": str(petsc_dir),
            "petsc_pc": str(pc_dir / "PETSc.pc"),
            "petsc_pc_ccompiler": pc_compiler,
            "compiler_executable": compiler_path,
            "compiler_resolved_target": compiler_target,
            "compiler_version": compiler_version,
            "compiler_show": compiler_show,
            "pkg_config_tokens": tokens,
            "source_path": str(ROOT / "src/solvers/petsc_lu_stage_bridge.c"),
            "source_sha256": hashlib.sha256(
                (ROOT / "src/solvers/petsc_lu_stage_bridge.c").read_bytes()
            ).hexdigest(),
            "compile_commands": [],
            "link_commands": [],
        }
    )

    petsc4py_root = Path(petsc4py.__file__).resolve().parent
    include_dirs = [
        str(petsc_dir / "include"),
        str(petsc4py_root / "include"),
        str(petsc4py_root),
    ]
    library_dirs: list[str] = []
    libraries: list[str] = []
    compile_args: list[str] = []
    link_args: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "-I" and index + 1 < len(tokens):
            index += 1
            include_dirs.append(tokens[index])
        elif token.startswith("-I"):
            include_dirs.append(token[2:])
        elif token == "-L" and index + 1 < len(tokens):
            index += 1
            library_dirs.append(tokens[index])
        elif token.startswith("-L"):
            library_dirs.append(token[2:])
        elif token.startswith("-l"):
            libraries.append(token[2:])
        elif token.startswith("-D"):
            compile_args.append(token)
        else:
            compile_args.append(token)
            if token.startswith("-Wl,"):
                link_args.append(token)
        index += 1

    return Extension(
        "petsc_lu_stage_bridge",
        [str(ROOT / "src/solvers/petsc_lu_stage_bridge.c")],
        include_dirs=include_dirs,
        library_dirs=library_dirs,
        libraries=libraries,
        extra_compile_args=compile_args,
        extra_link_args=link_args,
    )


class _RecordingBuildExt(build_ext):
    """Keep the actual native compile/link argv with the ignored build."""

    def build_extensions(self) -> None:
        compiler = self.compiler
        original_spawn = compiler.spawn

        def recorded_spawn(command: list[str], **kwargs: object) -> None:
            argv = [str(item) for item in command]
            phase = "compile_commands" if "-c" in argv else "link_commands"
            record = {"phase": phase.removesuffix("_commands"), "argv": argv}
            print(
                "PETSC_LU_STAGE_BUILD_COMMAND_JSON="
                + json.dumps(record, sort_keys=True, allow_nan=False),
                flush=True,
            )
            commands = BUILD_RECORD.get(phase)
            if not isinstance(commands, list):
                raise RuntimeError(f"build command list is missing: {phase}")
            commands.append(record)
            original_spawn(command, **kwargs)

        compiler.spawn = recorded_spawn
        try:
            super().build_extensions()
        finally:
            compiler.spawn = original_spawn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="ignored output directory for the extension and temporary objects",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    try:
        output_dir.relative_to(ROOT / "results")
    except ValueError as exc:
        raise SystemExit(
            "build output must be beneath the repository's ignored results/ tree"
        ) from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    extension = _extension(output_dir)
    compiler_path = str(BUILD_RECORD["compiler_executable"])
    compiler_argv = [compiler_path]
    os.environ["CC"] = shlex.join(compiler_argv)
    os.environ["LDSHARED"] = shlex.join([*compiler_argv, "-shared"])
    BUILD_RECORD["cc_environment"] = os.environ["CC"]
    BUILD_RECORD["ldshared_environment"] = os.environ["LDSHARED"]
    try:
        setup(
            name="myfenics-petsc-lu-stage-bridge",
            ext_modules=[extension],
            cmdclass={"build_ext": _RecordingBuildExt},
            script_args=[
                "build_ext",
                "--force",
                "--build-lib",
                str(output_dir / "lib"),
                "--build-temp",
                str(output_dir / "temp"),
            ],
        )
    finally:
        built_modules = sorted(
            (output_dir / "lib").glob("petsc_lu_stage_bridge*"),
            key=lambda path: path.name,
        )
        if len(built_modules) == 1 and built_modules[0].is_file():
            module_path = built_modules[0]
            BUILD_RECORD["extension_path"] = str(module_path)
            BUILD_RECORD["extension_sha256"] = hashlib.sha256(
                module_path.read_bytes()
            ).hexdigest()
        record_path = output_dir / "build_commands.json"
        record_path.write_text(
            json.dumps(BUILD_RECORD, indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
