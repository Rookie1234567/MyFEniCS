from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "benchmarks" / "scripts" / "run_task033_formal.ps1"


class Task033FormalCampaignScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_complete_clean_source_image_and_cgroup_preflight(self) -> None:
        text = self.text
        self.assertIn('[string]$RepositoryRoot = ""', text)
        self.assertIn("[string]::IsNullOrWhiteSpace($RepositoryRoot)", text)
        self.assertIn('"rev-parse", "HEAD"', text)
        self.assertIn("^[0-9a-f]{40}$", text)
        self.assertIn('"--untracked-files=all"', text)
        self.assertIn('"--ignored=no"', text)
        self.assertIn('"check-ignore", "--quiet", "--no-index"', text)
        self.assertIn('@("image", "inspect", $DockerImage)', text)
        self.assertIn("^sha256:[0-9a-f]{64}$", text)
        self.assertIn(
            "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d",
            text,
        )
        self.assertIn("if ($ImageDigest -ne $ExpectedImageDigest)", text)
        self.assertIn("memory.max", text)
        self.assertIn("memory.swap.max", text)
        self.assertIn("memory.swap.current", text)
        self.assertIn("import jsonschema", text)
        self.assertIn("host_aggregation_runtime", text)
        self.assertGreaterEqual(text.count("13958643712"), 2)

    def test_serial_13g_no_swap_and_explicit_native_exit_contract(self) -> None:
        text = self.text
        self.assertIn('"--memory", "13g"', text)
        self.assertIn('"--memory-swap", "13g"', text)
        self.assertIn('"GIT_CONFIG_COUNT=1"', text)
        self.assertIn('"GIT_CONFIG_KEY_0=core.autocrlf"', text)
        self.assertIn('"GIT_CONFIG_VALUE_0=true"', text)
        self.assertIn("container_git_checkout_normalization", text)
        self.assertIn('$WarningGiB = "10.678571428571429"', text)
        self.assertIn('$TerminateGiB = "12.071428571428571"', text)
        self.assertIn("[IO.FileShare]::None", text)
        self.assertIn("$LASTEXITCODE", text)
        self.assertIn("if ($exitCode -ne 0)", text)
        for forbidden in (
            "Start-Job",
            "ForEach-Object -Parallel",
            "Start-ThreadJob",
            "Start-Process",
        ):
            self.assertNotIn(forbidden, text)
        self.assertNotRegex(text, r"(?m)^\s*[^#\r\n]+(?:2>|\*>|>>)")

    def test_resume_markers_are_bound_to_source_image_and_output_hashes(self) -> None:
        text = self.text
        self.assertIn("task033-complete-$CommitSha.json", text)
        self.assertIn('schema_version = "task033.campaign-step-marker.v1"', text)
        self.assertIn("source_commit_full_sha = $CommitSha", text)
        self.assertIn("docker_image_digest = $ImageDigest", text)
        self.assertIn("Get-FileSha256 -Path $output", text)
        self.assertIn("Test-StepComplete", text)
        self.assertIn("Assert-FormalSourceStable -ExpectedSha $CommitSha", text)

    def test_case090_and_qep_campaign_matrix(self) -> None:
        text = self.text
        self.assertIn("foreach ($mpiSize in @(1, 2, 4))", text)
        self.assertIn("benchmarks.run_task033_case090_watchdog", text)
        self.assertIn("benchmarks.run_task033_case090_pde_core", text)
        self.assertIn('"aggregate"', text)
        self.assertIn('"--memory-summaries"', text)
        self.assertIn('"--require-pass"', text)
        self.assertIn(
            '$QepMaterials = @("air", "lossy_homogeneous", "stage4_xy")',
            text,
        )
        self.assertIn("$Degrees = @(1, 2, 3, 4)", text)
        self.assertIn("$QepNegativeMpiSizes = @(2, 4)", text)
        for level in ('Value = "5.0"', 'Value = "3.0"', 'Value = "2.5"'):
            self.assertIn(level, text)
        self.assertIn("-MpiSize 1", text)
        self.assertIn("-ExpectedTimeoutNegative", text)
        self.assertGreaterEqual(text.count("-CandidateModes 16"), 2)
        self.assertIn("Invoke-DockerQepP4Step", text)
        self.assertIn("-AllowP4ControlledNumericalNegative:($degree -eq 4)", text)
        self.assertIn("$exitCode -notin @(0, 2)", text)
        self.assertIn('$summary.return_code -ne 2', text)
        self.assertIn('$record.status -ne "measured_shard_failed"', text)
        self.assertIn("p1-p3 shards are strict passes", text)
        self.assertIn("p4 QEP solver-record SHA256", text)
        self.assertIn("max_requested_plus_8_or_2x", text)
        self.assertIn("$summary.terminated_for_timeout -eq $true", text)
        self.assertIn("$summary.terminated_for_memory -eq $false", text)
        self.assertIn("function Convert-ToNativeExitCode", text)
        self.assertIn("(($Code % 256) + 256) % 256", text)
        self.assertIn("$normalizedSummaryExit -eq $exitCode", text)
        self.assertIn(
            "$marker.native_exit_code -eq $normalizedSummaryExit", text
        )
        self.assertGreaterEqual(
            text.count("Remove-Item -LiteralPath $SummaryOutput -Force"), 2
        )
        self.assertNotIn("Negatives are never supplied to the aggregate", text)
        self.assertIn("record-backed, controlled numerical negative", text)
        self.assertIn('foreach ($negativeMpi in $QepNegativeMpiSizes)', text)
        self.assertIn('$slug = "stage4_xy_p2_h3"', text)
        self.assertIn(
            "$Case090AggregateEvidenceSha256", text
        )
        self.assertIn(
            "$case090AggregatePayload.evidence_sha256", text
        )
        self.assertNotIn(
            "$Case090AggregateSha256 = Get-FileSha256 -Path $Case090Aggregate",
            text,
        )

    def test_hybrid_uniform_anchors_graded_buffers_and_conditional_m240(self) -> None:
        text = self.text
        expected_uniform = {
            "p1_h5",
            "p1_h3",
            "p1_h2p5",
            "p1_h2",
            "p1_h1p5",
            "p2_h5",
            "p2_h3",
            "p2_h2p5",
            "p3_h5",
        }
        safe_matrix_match = re.search(
            r"\$safeUniform\s*=\s*@\((.*?)\n\s*\)",
            text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(safe_matrix_match)
        keys = set(re.findall(r'Key\s*=\s*"([^"]+)"', safe_matrix_match.group(1)))
        self.assertEqual(keys, expected_uniform)
        self.assertIn("foreach ($modeCount in @(80, 120, 160))", text)
        self.assertIn("-MpiSize 4", text)
        self.assertIn('"--incident-grazing-deg", "10.0"', text)
        self.assertIn('"--polarization-kind", "s"', text)
        self.assertIn('-SolverPath "augmented"', text)
        self.assertIn('"--compare-modal-schur"', text)
        self.assertIn('"--comparison-solver-path", "minimal"', text)
        self.assertIn('comparison.comparison_solver_path_argument -ne "minimal"', text)
        self.assertIn("augmented-vs-memory-minimal anchor did not qualify", text)
        self.assertIn("required_complete_mode_funnel", text)
        self.assertIn("requires_same_case_and_source_sha_across_funnel", text)
        self.assertIn("checks.common_candidate_basis_is_m160", text)
        self.assertIn("p2/h3 watchdog lacks complete same-SHA", text)
        self.assertIn('-Name "p2_h5_graded"', text)
        self.assertIn('-GradedReferenceH "5.0"', text)
        self.assertIn('-Name "p2_h3_graded"', text)
        self.assertIn('-GradedReferenceH "3.0"', text)
        self.assertIn('"buffer_10" = $uniformFunnels["p2_h3"]', text)
        for buffer_name in ("buffer_7p5", "buffer_5", "buffer_2p5"):
            self.assertIn(buffer_name, text)
        self.assertIn("$comparisons[0].mandatory_convergence_pass -eq $false", text)
        self.assertIn("conditional M240 is prohibited", text)
        self.assertIn("[switch]$AllowConditionalM240", text)
        self.assertIn('$Category -eq "uniform"', text)
        self.assertIn('$Degree -in @(3, 4)', text)
        self.assertIn("conditional M240 is restricted to explicitly authorized", text)
        self.assertIn("-AllowConditionalM240:$allowConditionalM240", text)
        self.assertIn("-RequestedModes 240", text)
        self.assertIn("-CandidateModes 240", text)
        self.assertIn('"--m160-funnel-evidence-file"', text)
        self.assertIn('"--m160-funnel-evidence-sha256"', text)

        h5_funnel = text.index('$gradedFunnels["p2_h5_graded"] = Invoke-HybridFunnel')
        h5_aggregate = text.index('-StepName "aggregate_adaptive_p2_h5"')
        h3_funnel = text.index('$gradedFunnels["p2_h3_graded"] = Invoke-HybridFunnel')
        h3_aggregate = text.index('-StepName "aggregate_adaptive_p2_h3"')
        self.assertLess(h5_funnel, h5_aggregate)
        self.assertLess(h5_aggregate, h3_funnel)
        self.assertLess(h3_funnel, h3_aggregate)

        graded_h5_block = text[h5_funnel:h5_aggregate]
        h5_gate_block = text[h5_aggregate:h3_funnel]
        graded_h3_block = text[h3_funnel:h3_aggregate]
        buffer_start = text.index("# Phase 5:")
        buffer_end = text.index("# Phase 6:")
        self.assertNotIn("-AllowConditionalM240", graded_h5_block)
        self.assertNotIn("-AllowConditionalM240", graded_h3_block)
        self.assertNotIn("-AllowConditionalM240", text[buffer_start:buffer_end])
        self.assertIn(
            "Assert-AdaptiveFormalPass -Path $adaptiveH5 -ExpectedReferenceH 5.0",
            h5_gate_block,
        )
        self.assertIn(
            "Assert-AdaptiveFormalPass -Path $adaptiveH3 -ExpectedReferenceH 3.0",
            text[h3_aggregate:buffer_start],
        )

        self.assertIn("bounded clean wall-timeout diagnostics", text)
        self.assertIn("prove only the watchdog/source/resource", text)
        self.assertNotIn("known distributed PEP/MUMPS boundary", text)

    def test_primary_aggregates_projection_manifest_and_checker(self) -> None:
        text = self.text
        self.assertIn("benchmarks.run_task033_formal_records", text)
        self.assertIn('$gradedKey in @("p2_h5_graded", "p2_h3_graded")', text)
        self.assertIn('$equalAccuracyCommand += "--require-qualified"', text)
        self.assertIn("Invoke-HostJsonCaptureStep", text)
        self.assertIn("Invoke-HostFileStep", text)
        self.assertIn("[string]$HostPythonExecutable", text)
        for subcommand in (
            "qep-order-study",
            "uniform-matrix",
            "adaptive",
            "buffer-tradeoff",
            "publication-descriptor",
        ):
            self.assertIn(f'"{subcommand}"', text)
        self.assertIn("benchmarks.run_task033_variable_p_audit", text)
        self.assertIn("benchmarks.run_task033_equal_accuracy", text)
        self.assertIn("benchmarks.run_task033_one_tib_projection", text)
        self.assertIn(
            '"qep-order-study", "--mpi-size", "1",\n'
            '        "--repo-root", $RepoRoot',
            text,
        )
        self.assertIn(
            '"uniform-matrix",\n        "--repo-root", $RepoRoot',
            text,
        )
        self.assertGreaterEqual(text.count('"--repo-root", $RepoRoot'), 10)
        self.assertIn('"--watchdog"', text)
        self.assertIn('"p2_h3=$p2H3SelectedWatchdog"', text)
        self.assertIn('"--compression-evidence"', text)
        self.assertIn("$equalAccuracy", text)
        self.assertIn('"aggregate_one_tib_projection"', text)
        self.assertIn('"aggregate_final_outcome"', text)
        self.assertIn("benchmarks.run_task033_final_outcome", text)
        self.assertIn('"--qep-mpi2-timeout-negative"', text)
        self.assertIn('"--qep-mpi4-timeout-negative"', text)
        self.assertIn('"--augmented-vs-minimal-p1"', text)
        self.assertIn('"--augmented-vs-minimal-p3"', text)
        self.assertIn('"--expected-source-sha"', text)
        self.assertIn('"--require-nonfailed"', text)
        self.assertIn('"aggregate_formal_evidence_manifest"', text)
        self.assertIn('"verify_formal_evidence_manifest"', text)
        self.assertIn('"formal-manifest"', text)
        self.assertIn('"--formal-manifest"', text)
        self.assertIn('"--require-formal"', text)
        self.assertIn('"case090_clean_core" = $Case090Aggregate', text)
        self.assertIn(
            '"qep_mpi2_timeout_negative" = (Join-Path $ArtifactRootHost',
            text,
        )
        self.assertIn(
            '"qep_mpi4_timeout_negative" = (Join-Path $ArtifactRootHost',
            text,
        )
        self.assertIn('"augmented_vs_minimal_p1" = $p1Anchor', text)
        self.assertIn('"augmented_vs_minimal_p3" = $p3Anchor', text)
        self.assertIn('"equal_accuracy" = $equalAccuracy', text)
        self.assertIn('"one_tib_projection" = $oneTib', text)
        self.assertIn('"final_outcome" = $finalOutcome', text)
        self.assertNotIn('"qep_mpi_timeout_negative" =', text)
        self.assertIn('"aggregate_formal_publication_descriptor"', text)
        self.assertLess(
            text.index('"aggregate_final_outcome"'),
            text.index('"aggregate_formal_evidence_manifest"'),
        )
        self.assertLess(
            text.index('"verify_formal_evidence_manifest"'),
            text.index('"aggregate_formal_publication_descriptor"'),
        )
        self.assertNotIn("one_tib_deferred_pending", text)

    def test_powershell_parser_accepts_script_when_available(self) -> None:
        executable = shutil.which("pwsh") or shutil.which("powershell")
        if executable is None:
            self.skipTest("PowerShell parser is not available")
        script_path = str(SCRIPT).replace("'", "''")
        command = (
            "$tokens=$null; $errors=$null; "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{script_path}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count -ne 0) { "
            "$errors | ForEach-Object { Write-Error $_.Message }; exit 2 }"
        )
        completed = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
