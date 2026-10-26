#!/usr/bin/env python3
"""Extract bounded, hash-bound excerpts from preserved V9 text only."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
RAW = ROOT / "benchmarks/artifacts/task43/v9_resume_preparation/raw"
SUMMARY_PATH = ROOT / "docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/root_s1_review.json"
SUMMARY = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
STATIC_SUMMARY_PATH = ROOT / "docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/s1_static_summary.json"
STATIC_SUMMARY = json.loads(STATIC_SUMMARY_PATH.read_text(encoding="utf-8"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_info(rel: str) -> dict[str, object]:
    path = ROOT / rel
    data = path.read_bytes()
    return {"path": rel, "sha256": sha(data), "size_bytes": len(data)}


SCRIPT_BY_RECORD = {
    "activation_mca": "collect_activation_mca.sh",
    "login_sources": "inspect_login_mca_sources.sh",
    "login_selector_env": "record_login_selector_env.sh",
    "mca_registry_strings": "inspect_mca_registry_strings.sh",
    "mca_param_paths": "inspect_mca_param_paths.sh",
    "inspect_mca_override_files": "inspect_mca_override_files.sh",
    "inspect_sysconfdir_ownership": "inspect_sysconfdir_ownership.sh",
    "map_needed_sonames": "map_needed_sonames.sh",
    "recheck_15_elf": "recheck_15_elf.sh",
    "map_direct_needed_paths": "map_direct_needed_paths.sh",
}

MATCHES = {
    "activation_mca": re.compile(r"^(scope=|utc=|--- tracked activation|/home/fenics/Projects/NN-Lab-V2/scripts/|[0-9a-f]{64}  /home/fenics/Projects/NN-Lab-V2/scripts/|\d+:export (LD_LIBRARY_PATH|PYTHONPATH)=|--- venv activation|/home/fenics/Projects/Maxwell3D-Lab/.+|UNSET (OMPI_MCA_|PMIX_MCA_|PRTE_MCA_|ORTE_MCA_|HWLOC_COMPONENTS|OPAL_PREFIX|LD_LIBRARY_PATH|LD_PRELOAD)|PRESENT /etc/openmpi|/etc/openmpi/openmpi-mca-params.conf|pml =|btl =|mtl =)"),
    "login_sources": re.compile(r"^(scope=|utc=|---|# /etc/profile|if \[ -d /etc/profile.d \]|for i in /etc/profile.d|\. \$i|# ~/.profile|# ~/.bashrc|case \$-|return|PRESENT /etc/profile|PRESENT /etc/bash|PRESENT /home/fenics/\.(profile|bashrc)|.*gnomerc.*|.*non-interactive.*)"),
    "login_selector_env": re.compile(r"^(scope=|utc=|SET |UNSET (XDG_SESSION_TYPE|XDG_CURRENT_DESKTOP|DESKTOP_SESSION|GNOME_DESKTOP_SESSION_ID|XDG_CONFIG_HOME|BASH_ENV|ENV|OMPI_MCA_|PMIX_MCA_|PRTE_MCA_|ORTE_MCA_|HWLOC_COMPONENTS|LD_LIBRARY_PATH|LD_PRELOAD))"),
    "mca_registry_strings": re.compile(r"^(scope=|utc=|FILE |[0-9a-f]{64}  |OMPI_MCA_|PMIX_MCA_|PRTE_MCA_|ORTE_MCA_|.*mca_base_(component_path|env_list|envar_file_prefix|param_file_path|param_file_path_force|param_file_prefix|override_param_file).*)"),
    "mca_param_paths": re.compile(r"^(scope=|utc=|FILE |[0-9a-f]{64}  |.*(\.openmpi|openmpi-mca-params|mca_base_(component_path|env_list|envar_file_prefix|param_file_path|param_file_path_force|param_file_prefix|override_param_file)).*)"),
    "inspect_mca_override_files": re.compile(r"^(scope=|utc=|---|PRESENT |ABSENT |UNSET |SET |/etc/openmpi/openmpi-mca-params.conf|[0-9a-f]{64}  /etc/openmpi|\d+:(pml|btl|mtl) = )"),
    "inspect_sysconfdir_ownership": re.compile(r"^(scope=|utc=|---|openmpi-bin:|openmpi-common|PACKAGE |/etc/openmpi|%s/.*openmpi.*)"),
}

RECORDS = (
    "activation_mca",
    "login_sources",
    "login_selector_env",
    "mca_registry_strings",
    "mca_param_paths",
    "inspect_mca_override_files",
    "inspect_sysconfdir_ownership",
    "map_needed_sonames",
    "recheck_15_elf",
    "map_direct_needed_paths",
)

records: list[dict[str, object]] = []
for name in RECORDS:
    stdout_rel = f"benchmarks/artifacts/task43/v9_resume_preparation/raw/{name}.stdout"
    stdout_path = ROOT / stdout_rel
    stdout_data = stdout_path.read_bytes()
    text = stdout_data.decode("utf-8", errors="replace")
    selector = MATCHES.get(name)
    excerpt = []
    if name == "activation_mca":
        # Preserve the exact activation/venv selector lines requested by review.
        excerpt = [
            {"line": number, "text": line}
            for number, line in enumerate(text.splitlines(), 1)
            if 1 <= number <= 29 or 44 <= number <= 82
        ]
    elif selector:
        excerpt = [
            {"line": number, "text": line}
            for number, line in enumerate(text.splitlines(), 1)
            if selector.search(line)
        ]
    script_name = SCRIPT_BY_RECORD[name]
    script_rel = f"docs/task43_hp_adaptivity/outcomes/records/v10_static_evidence_sources/collector_snapshots/{script_name}"
    files: dict[str, object] = {
        "stdout": file_info(stdout_rel),
        "collector_snapshot": file_info(script_rel),
    }
    for suffix in ("command.txt", "stderr", "exit_code", "time", "started.txt", "finished.txt"):
        rel = f"benchmarks/artifacts/task43/v9_resume_preparation/raw/{name}.{suffix}"
        if (ROOT / rel).is_file():
            files[suffix.removesuffix(".txt")] = file_info(rel)
    command_rel = f"benchmarks/artifacts/task43/v9_resume_preparation/raw/{name}.command.txt"
    command = (ROOT / command_rel).read_text(encoding="utf-8").strip() if (ROOT / command_rel).is_file() else None
    exit_rel = f"benchmarks/artifacts/task43/v9_resume_preparation/raw/{name}.exit_code"
    exit_code = (ROOT / exit_rel).read_text(encoding="utf-8").strip() if (ROOT / exit_rel).is_file() else None
    records.append({
        "record": name,
        "files": files,
        "command_text": command,
        "recorded_exit_code": exit_code,
        "bounded_saved_stdout_excerpt": excerpt,
    })

payload = {
    "schema": "task43.v10.saved_v9_input_context_excerpt.v1",
    "scope": "Offline extraction from preserved V9 raw text and existing V9 S1 review only. No source activation, native import, environment probe, ELF inspection, or capture-script execution.",
    "source_review": {
        "path": "docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/root_s1_review.json",
        "sha256": sha(SUMMARY_PATH.read_bytes()),
        "status": SUMMARY.get("status"),
        "issues": SUMMARY.get("issues"),
        "historical_input_conclusion_only": SUMMARY.get("input_conclusion"),
        "interpretation": "Quoted V9 S1 conclusion, not a new V10 environment check or a claim about a worker process."
    },
    "v9_static_summary": {
        "path": "docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/s1_static_summary.json",
        "sha256": sha(STATIC_SUMMARY_PATH.read_bytes()),
        "historical_activation_and_mca": STATIC_SUMMARY.get("activation_and_mca", {}),
        "historical_elf_recheck": STATIC_SUMMARY.get("elf_and_dependency_map", {}).get("frozen_elf_recheck", {})
    },
    "raw_records": records,
    "output": str(OUT),
}
OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"output": str(OUT), "records": len(records), "sha256": sha(OUT.read_bytes())}, sort_keys=True))
