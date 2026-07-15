[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$DockerExecutable = "docker",
    [string]$HostPythonExecutable = "python",
    [string]$DockerImage = "myfenics-stage4:task28",
    [string]$ArtifactRoot = (
        "benchmarks/artifacts/cases/091/task033_formal_campaign"
    ),
    [string]$HostEnvironmentId = "windows-docker-desktop",
    [double]$Case090TimeoutSeconds = 86400.0,
    [double]$QepTimeoutSeconds = 3600.0,
    [double]$QepNegativeTimeoutSeconds = 1.0,
    [double]$HybridTimeoutSeconds = 21600.0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# Native nonzero codes are inspected explicitly below.  This is required for
# the intentional MPI2/MPI4 timeout-negative QEP steps.
$PSNativeCommandUseErrorActionPreference = $false

$ExpectedMemoryMaxBytes = 13958643712
$ExpectedImageDigest = (
    "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d"
)
$WarningGiB = "10.678571428571429"
$TerminateGiB = "12.071428571428571"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$RepositoryRoot = if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
} else {
    $RepositoryRoot
}
$RepoRoot = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd(
    [char[]]@(47, 92)
)
$ArtifactRootHost = if ([IO.Path]::IsPathRooted($ArtifactRoot)) {
    [IO.Path]::GetFullPath($ArtifactRoot)
} else {
    [IO.Path]::GetFullPath((Join-Path $RepoRoot $ArtifactRoot))
}

function Invoke-NativeCapture {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )

    $captured = @(& $FilePath @ArgumentList)
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
        ExitCode = $exitCode
        Text = ($captured -join "`n")
    }
}

function Invoke-NativeStreaming {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )

    & $FilePath @ArgumentList | Out-Host
    return $LASTEXITCODE
}

function Invoke-GitCapture {
    param([Parameter(Mandatory = $true)][string[]]$ArgumentList)

    Push-Location $RepoRoot
    try {
        $result = Invoke-NativeCapture -FilePath "git" -ArgumentList $ArgumentList
    } finally {
        Pop-Location
    }
    return $result
}

function Get-FormalSourceSha {
    $topLevel = Invoke-GitCapture -ArgumentList @(
        "rev-parse", "--show-toplevel"
    )
    if ($topLevel.ExitCode -ne 0) {
        throw "git rev-parse --show-toplevel failed."
    }
    $observedRoot = [IO.Path]::GetFullPath($topLevel.Text.Trim()).TrimEnd(
        [char[]]@(47, 92)
    )
    if (-not $observedRoot.Equals(
        $RepoRoot,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "RepositoryRoot is not the Git top level: $RepoRoot"
    }

    $head = Invoke-GitCapture -ArgumentList @("rev-parse", "HEAD")
    if ($head.ExitCode -ne 0) {
        throw "git rev-parse HEAD failed with exit code $($head.ExitCode)."
    }
    $sha = $head.Text.Trim().ToLowerInvariant()
    if ($sha -notmatch '^[0-9a-f]{40}$') {
        throw "Task033 formal campaign requires one full 40-character Git SHA."
    }

    $status = Invoke-GitCapture -ArgumentList @(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignored=no"
    )
    if ($status.ExitCode -ne 0) {
        throw "Complete nonignored Git status failed with exit code $($status.ExitCode)."
    }
    if ($status.Text.Trim().Length -ne 0) {
        throw (
            "Formal campaign requires a completely clean nonignored worktree. " +
            "Commit or remove tracked changes and nonignored untracked files first.`n" +
            $status.Text
        )
    }
    return $sha
}

function Assert-FormalSourceStable {
    param([Parameter(Mandatory = $true)][string]$ExpectedSha)

    $observed = Get-FormalSourceSha
    if ($observed -ne $ExpectedSha) {
        throw "Git HEAD changed during the campaign: $ExpectedSha -> $observed."
    }
}

function Convert-ToRepoRelativePath {
    param([Parameter(Mandatory = $true)][string]$HostPath)

    $full = [IO.Path]::GetFullPath($HostPath)
    $prefix = $RepoRoot + [IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Formal artifact is outside the repository: $full"
    }
    return $full.Substring($prefix.Length).Replace('\', '/')
}

function Convert-ToContainerPath {
    param([Parameter(Mandatory = $true)][string]$HostPath)

    return "/work/$(Convert-ToRepoRelativePath -HostPath $HostPath)"
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )

    $parent = Split-Path -Parent $Path
    if ($parent) {
        [IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    $temporary = "$Path.tmp-$PID"
    [IO.File]::WriteAllText($temporary, $Text, $Utf8NoBom)
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-StepMarkerPath {
    param([Parameter(Mandatory = $true)][string]$PrimaryOutput)

    return "$PrimaryOutput.task033-complete-$CommitSha.json"
}

function Test-StepComplete {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][string[]]$Outputs
    )

    $markerPath = Get-StepMarkerPath -PrimaryOutput $Outputs[0]
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        return $false
    }
    try {
        $marker = Get-Content -Raw -LiteralPath $markerPath | ConvertFrom-Json
        if (
            $marker.schema_version -ne "task033.campaign-step-marker.v1" -or
            $marker.step_name -ne $StepName -or
            $marker.source_commit_full_sha -ne $CommitSha -or
            $marker.docker_image_digest -ne $ImageDigest
        ) {
            return $false
        }
        $descriptors = @($marker.outputs)
        if ($descriptors.Count -ne $Outputs.Count) {
            return $false
        }
        foreach ($output in $Outputs) {
            if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
                return $false
            }
            $relative = Convert-ToRepoRelativePath -HostPath $output
            $descriptor = @(
                $descriptors | Where-Object { $_.path -eq $relative }
            )
            if (
                $descriptor.Count -ne 1 -or
                $descriptor[0].sha256 -ne (Get-FileSha256 -Path $output)
            ) {
                return $false
            }
        }
    } catch {
        return $false
    }
    Write-Host "[resume] $StepName already completed for $CommitSha"
    return $true
}

function Complete-Step {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][string[]]$Outputs,
        [Parameter(Mandatory = $true)][int]$ExitCode
    )

    Assert-FormalSourceStable -ExpectedSha $CommitSha
    $descriptors = @()
    foreach ($output in $Outputs) {
        if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
            throw "Step $StepName did not create required output $output."
        }
        $descriptors += [ordered]@{
            path = Convert-ToRepoRelativePath -HostPath $output
            sha256 = Get-FileSha256 -Path $output
        }
    }
    $marker = [ordered]@{
        schema_version = "task033.campaign-step-marker.v1"
        step_name = $StepName
        source_commit_full_sha = $CommitSha
        docker_image = $DockerImage
        docker_image_digest = $ImageDigest
        native_exit_code = $ExitCode
        completed_utc = [DateTime]::UtcNow.ToString("o")
        outputs = $descriptors
    }
    $markerPath = Get-StepMarkerPath -PrimaryOutput $Outputs[0]
    $rendered = ($marker | ConvertTo-Json -Depth 8) + "`n"
    Write-Utf8NoBom -Path $markerPath -Text $rendered
}

function Get-DockerRunArguments {
    param([Parameter(Mandatory = $true)][string[]]$ContainerCommand)

    $mount = "type=bind,source=$RepoRoot,target=/work"
    return @(
        "run", "--rm",
        "--memory", "13g",
        "--memory-swap", "13g",
        "--mount", $mount,
        "--workdir", "/work",
        "--env", "OMPI_ALLOW_RUN_AS_ROOT=1",
        "--env", "OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1",
        $ImageDigest
    ) + $ContainerCommand
}

function Invoke-DockerFileStep {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][string[]]$ContainerCommand,
        [Parameter(Mandatory = $true)][string[]]$Outputs,
        [scriptblock]$Validator
    )

    if (Test-StepComplete -StepName $StepName -Outputs $Outputs) {
        return
    }
    Assert-FormalSourceStable -ExpectedSha $CommitSha
    Write-Host "[run] $StepName"
    $dockerArguments = Get-DockerRunArguments -ContainerCommand $ContainerCommand
    $exitCode = Invoke-NativeStreaming `
        -FilePath $DockerExecutable `
        -ArgumentList $dockerArguments
    if ($exitCode -ne 0) {
        throw "Step $StepName failed with native exit code $exitCode."
    }
    if ($null -ne $Validator) {
        & $Validator $Outputs
    }
    Complete-Step -StepName $StepName -Outputs $Outputs -ExitCode $exitCode
}

function Invoke-DockerTimeoutNegativeStep {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][string[]]$ContainerCommand,
        [Parameter(Mandatory = $true)][string]$SummaryOutput
    )

    $outputs = @($SummaryOutput)
    if (Test-StepComplete -StepName $StepName -Outputs $outputs) {
        return
    }
    Assert-FormalSourceStable -ExpectedSha $CommitSha
    Write-Host "[run expected-timeout-negative] $StepName"
    $dockerArguments = Get-DockerRunArguments -ContainerCommand $ContainerCommand
    $exitCode = Invoke-NativeStreaming `
        -FilePath $DockerExecutable `
        -ArgumentList $dockerArguments
    if ($exitCode -eq 0) {
        throw "Timeout-negative step $StepName unexpectedly returned success."
    }
    if (-not (Test-Path -LiteralPath $SummaryOutput -PathType Leaf)) {
        throw "Timeout-negative step $StepName produced no watchdog summary."
    }
    $summary = Get-Content -Raw -LiteralPath $SummaryOutput | ConvertFrom-Json
    $validTimeoutNegative = (
        $summary.status -eq "formal_not_pass" -and
        $summary.terminated_for_timeout -eq $true -and
        $summary.terminated_for_memory -eq $false -and
        $summary.terminated_for_authority_unreadable -eq $false -and
        $summary.memory_authority_pass -eq $true -and
        $summary.no_swap -eq $true -and
        $summary.source_gate.pass -eq $true -and
        $summary.launch_gate.pass -eq $true
    )
    if (-not $validTimeoutNegative) {
        throw "Step $StepName was not the required clean timeout-only negative."
    }
    Complete-Step -StepName $StepName -Outputs $outputs -ExitCode $exitCode
}

function Invoke-DockerJsonCaptureStep {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][string[]]$ContainerCommand,
        [Parameter(Mandatory = $true)][string]$Output
    )

    $outputs = @($Output)
    if (Test-StepComplete -StepName $StepName -Outputs $outputs) {
        return
    }
    Assert-FormalSourceStable -ExpectedSha $CommitSha
    Write-Host "[aggregate] $StepName"
    $dockerArguments = Get-DockerRunArguments -ContainerCommand $ContainerCommand
    $captured = Invoke-NativeCapture `
        -FilePath $DockerExecutable `
        -ArgumentList $dockerArguments
    if ($captured.ExitCode -ne 0) {
        throw "Aggregate $StepName failed with exit code $($captured.ExitCode)."
    }
    try {
        $captured.Text | ConvertFrom-Json | Out-Null
    } catch {
        throw "Aggregate $StepName did not emit one valid JSON object."
    }
    Write-Utf8NoBom -Path $Output -Text ($captured.Text.Trim() + "`n")
    Complete-Step `
        -StepName $StepName `
        -Outputs $outputs `
        -ExitCode $captured.ExitCode
}

function Invoke-HostJsonCaptureStep {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][string[]]$PythonArguments,
        [Parameter(Mandatory = $true)][string]$Output
    )

    $outputs = @($Output)
    if (Test-StepComplete -StepName $StepName -Outputs $outputs) {
        return
    }
    Assert-FormalSourceStable -ExpectedSha $CommitSha
    Write-Host "[host aggregate] $StepName"
    Push-Location $RepoRoot
    try {
        $captured = Invoke-NativeCapture `
            -FilePath $HostPythonExecutable `
            -ArgumentList $PythonArguments
    } finally {
        Pop-Location
    }
    if ($captured.ExitCode -ne 0) {
        throw "Host aggregate $StepName failed with exit code $($captured.ExitCode)."
    }
    try {
        $captured.Text | ConvertFrom-Json | Out-Null
    } catch {
        throw "Host aggregate $StepName did not emit one valid JSON object."
    }
    Write-Utf8NoBom -Path $Output -Text ($captured.Text.Trim() + "`n")
    Complete-Step `
        -StepName $StepName `
        -Outputs $outputs `
        -ExitCode $captured.ExitCode
}

function Invoke-HostFileStep {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][string[]]$PythonArguments,
        [Parameter(Mandatory = $true)][string[]]$Outputs
    )

    if (Test-StepComplete -StepName $StepName -Outputs $Outputs) {
        return
    }
    Assert-FormalSourceStable -ExpectedSha $CommitSha
    Write-Host "[host record] $StepName"
    Push-Location $RepoRoot
    try {
        $exitCode = Invoke-NativeStreaming `
            -FilePath $HostPythonExecutable `
            -ArgumentList $PythonArguments
    } finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw "Host record $StepName failed with native exit code $exitCode."
    }
    Complete-Step -StepName $StepName -Outputs $Outputs -ExitCode $exitCode
}

function Assert-WatchdogPass {
    param([Parameter(Mandatory = $true)][string[]]$Outputs)

    $summary = Get-Content -Raw -LiteralPath $Outputs[0] | ConvertFrom-Json
    if (
        $summary.status -ne "measured_shard_pass" -or
        $summary.formal_pass -ne $true -or
        $summary.return_code -ne 0 -or
        $summary.no_swap -ne $true -or
        $summary.terminated_for_memory -ne $false -or
        $summary.terminated_for_timeout -ne $false -or
        $summary.memory_authority_pass -ne $true -or
        $summary.source_gate.pass -ne $true -or
        $summary.launch_gate.pass -ne $true
    ) {
        throw "External watchdog summary is not a formal measured pass: $($Outputs[0])"
    }
}

function Assert-P2H3Requalification {
    param(
        [Parameter(Mandatory = $true)][string[]]$Outputs,
        [Parameter(Mandatory = $true)][int]$ExpectedRequestedModes
    )

    $summary = Get-Content -Raw -LiteralPath $Outputs[0] | ConvertFrom-Json
    $requalification = $summary.task033_anchor_requalification
    $requiredModes = @($requalification.required_complete_mode_funnel)
    $requalificationChecks = @(
        $requalification.checks.PSObject.Properties.Value
    )
    if (
        $requalification.requested -ne $true -or
        $requalification.allowed -ne $true -or
        $requalification.reason -ne (
            "Task033 same-SHA formal requalification"
        ) -or
        $requalification.case_identity -ne (
            "p2_h3_10_110_primary_modal_schur_memory_minimal"
        ) -or
        $requalification.source_commit_full_sha -ne $CommitSha -or
        $requalification.current_requested_mode -ne $ExpectedRequestedModes -or
        ($requiredModes -join ",") -ne "80,120,160" -or
        (
            $requalification.requires_same_case_and_source_sha_across_funnel `
                -ne $true
        ) -or
        $requalification.does_not_replace_task032_anchor -ne $true -or
        $requalification.checks.common_candidate_basis_is_m160 -ne $true -or
        $requalificationChecks.Count -eq 0 -or
        @(
            $requalificationChecks | Where-Object { $_ -ne $true }
        ).Count -ne 0
    ) {
        throw "p2/h3 watchdog lacks complete same-SHA requalification."
    }
}

function Assert-MinimalComparisonPass {
    param([Parameter(Mandatory = $true)][string[]]$Outputs)

    $record = Get-Content -Raw -LiteralPath $Outputs[0] | ConvertFrom-Json
    $measurements = $record.measurements
    $comparison = $measurements.modal_schur_comparison
    $comparisonGates = @($comparison.gates.PSObject.Properties.Value)
    if (
        $measurements.hybrid_system.primary_solver_path -ne "augmented" -or
        $comparison.status -ne "pass" -or
        $comparison.comparison_solver_path -ne (
            "modal-schur-memory-minimal"
        ) -or
        $comparison.comparison_solver_path_argument -ne "minimal" -or
        $comparison.dense_interface_square_formed -ne $false -or
        $comparisonGates.Count -eq 0 -or
        @($comparisonGates | Where-Object { $_ -ne $true }).Count -ne 0
    ) {
        throw "Task033 augmented-vs-memory-minimal anchor did not qualify."
    }
}

function Invoke-Task033Watchdog {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][ValidateSet("qep", "hybrid")][string]$Target,
        [Parameter(Mandatory = $true)][int]$Degree,
        [Parameter(Mandatory = $true)][string]$HNm,
        [Parameter(Mandatory = $true)][int]$MpiSize,
        [Parameter(Mandatory = $true)][int]$RequestedModes,
        [Parameter(Mandatory = $true)][int]$CandidateModes,
        [Parameter(Mandatory = $true)][string]$SummaryOutput,
        [Parameter(Mandatory = $true)][string]$AttemptRoot,
        [string]$MaterialKind,
        [string]$SolverPath = "modal-schur-memory-minimal",
        [string]$BottomInterfaceNm = "10.0",
        [string]$TopInterfaceNm = "110.0",
        [string]$GradedReferenceH,
        [switch]$AnchorRequalification,
        [switch]$CompareModalSchur,
        [string]$M160FunnelEvidence,
        [string]$M160FunnelSha256,
        [double]$TimeoutSeconds = 3600.0,
        [switch]$ExpectedTimeoutNegative
    )

    $attemptRun = Join-Path $AttemptRoot (
        "attempt_" + [Guid]::NewGuid().ToString("N")
    )
    $command = @(
        "python", "-m", "benchmarks.run_task033_memory_watchdog",
        "--target", $Target,
        "--case-label", $StepName,
        "--degree", "$Degree",
        "--h-nm", $HNm,
        "--mpi-size", "$MpiSize",
        "--requested-modes", "$RequestedModes",
        "--candidate-modes", "$CandidateModes",
        "--verified-clean-sha", $CommitSha,
        "--poll-interval", "0.25",
        "--warning-gib", $WarningGiB,
        "--terminate-gib", $TerminateGiB,
        "--timeout-seconds", "$TimeoutSeconds",
        "--artifact-root", (Convert-ToContainerPath -HostPath $AttemptRoot),
        "--run-dir", (Convert-ToContainerPath -HostPath $attemptRun),
        "--summary-output", (Convert-ToContainerPath -HostPath $SummaryOutput),
        "--container-image", $DockerImage,
        "--container-digest", $ImageDigest,
        "--host-environment-id", $HostEnvironmentId
    )
    if ($Target -eq "qep") {
        $command += @("--material-kind", $MaterialKind)
    } else {
        $command += @(
            "--solver-path", $SolverPath,
            "--bottom-interface-nm", $BottomInterfaceNm,
            "--top-interface-nm", $TopInterfaceNm,
            "--incident-grazing-deg", "10.0",
            "--polarization-kind", "s",
            "--resource-matrix",
            "/work/benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/resource_matrix.json"
        )
        if ($GradedReferenceH) {
            $command += @(
                "--graded-reference-h", $GradedReferenceH,
                "--graded-coarse-factor", "2.0"
            )
        }
        if ($AnchorRequalification) {
            $command += "--task033-same-sha-anchor-requalification"
        }
        if ($CompareModalSchur) {
            $command += @(
                "--compare-modal-schur",
                "--comparison-solver-path", "minimal"
            )
        }
        if ($M160FunnelEvidence) {
            $command += @(
                "--m160-funnel-evidence-file",
                (Convert-ToContainerPath -HostPath $M160FunnelEvidence),
                "--m160-funnel-evidence-sha256", $M160FunnelSha256
            )
        }
    }
    if ($Degree -ge 3) {
        $command += @(
            "--high-order-core-evidence-file",
            (Convert-ToContainerPath -HostPath $Case090Aggregate),
            "--high-order-core-evidence-sha256", $Case090AggregateSha256
        )
    }

    [IO.Directory]::CreateDirectory((Split-Path -Parent $SummaryOutput)) | Out-Null
    [IO.Directory]::CreateDirectory($AttemptRoot) | Out-Null
    if ($ExpectedTimeoutNegative) {
        Invoke-DockerTimeoutNegativeStep `
            -StepName $StepName `
            -ContainerCommand $command `
            -SummaryOutput $SummaryOutput
    } else {
        $requalificationRequired = [bool]$AnchorRequalification
        $minimalComparisonRequired = [bool]$CompareModalSchur
        $requestedModesForValidation = $RequestedModes
        $watchdogValidator = {
            param([string[]]$Outputs)

            Assert-WatchdogPass -Outputs $Outputs
            if ($requalificationRequired) {
                Assert-P2H3Requalification `
                    -Outputs $Outputs `
                    -ExpectedRequestedModes $requestedModesForValidation
            }
            if ($minimalComparisonRequired) {
                Assert-MinimalComparisonPass -Outputs $Outputs
            }
        }.GetNewClosure()
        Invoke-DockerFileStep `
            -StepName $StepName `
            -ContainerCommand $command `
            -Outputs @($SummaryOutput) `
            -Validator $watchdogValidator
    }
}

function Invoke-HybridFunnel {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Category,
        [Parameter(Mandatory = $true)][int]$Degree,
        [Parameter(Mandatory = $true)][string]$HNm,
        [string]$BottomInterfaceNm = "10.0",
        [string]$TopInterfaceNm = "110.0",
        [string]$GradedReferenceH,
        [switch]$AnchorRequalification
    )

    $root = Join-Path $ArtifactRootHost "hybrid/$Category/$Name"
    [IO.Directory]::CreateDirectory($root) | Out-Null
    $summaries = @()
    foreach ($modeCount in @(80, 120, 160)) {
        $modeLabel = "m{0:d3}" -f $modeCount
        $modeRoot = Join-Path $root $modeLabel
        $summary = Join-Path $modeRoot "watchdog_summary.json"
        $summaries += $summary
        Invoke-Task033Watchdog `
            -StepName "hybrid_${Category}_${Name}_${modeLabel}" `
            -Target "hybrid" `
            -Degree $Degree `
            -HNm $HNm `
            -MpiSize 4 `
            -RequestedModes $modeCount `
            -CandidateModes 160 `
            -SummaryOutput $summary `
            -AttemptRoot (Join-Path $modeRoot "attempts") `
            -SolverPath "modal-schur-memory-minimal" `
            -BottomInterfaceNm $BottomInterfaceNm `
            -TopInterfaceNm $TopInterfaceNm `
            -GradedReferenceH $GradedReferenceH `
            -AnchorRequalification:$AnchorRequalification `
            -TimeoutSeconds $HybridTimeoutSeconds
    }

    $m160Funnel = Join-Path $root "funnel_m80_m120_m160.json"
    $funnelCommand = @(
        "python", "-m", "benchmarks.run_task033_hybrid_funnel"
    )
    foreach ($summary in $summaries) {
        $funnelCommand += Convert-ToContainerPath -HostPath $summary
    }
    $funnelCommand += @(
        "--output", (Convert-ToContainerPath -HostPath $m160Funnel)
    )
    Invoke-DockerFileStep `
        -StepName "hybrid_${Category}_${Name}_aggregate_m160" `
        -ContainerCommand $funnelCommand `
        -Outputs @($m160Funnel)

    $provisional = Get-Content -Raw -LiteralPath $m160Funnel | ConvertFrom-Json
    if ($provisional.status -eq "qualified") {
        return $m160Funnel
    }
    $expectedFailure = (
        "M120->M160 did not converge and no qualifying M160->M240 result exists"
    )
    $comparisons = @(
        $provisional.comparisons | Where-Object {
            $_.previous_mode_count -eq 120 -and $_.current_mode_count -eq 160
        }
    )
    $failures = @($provisional.failures)
    $measuredNonconvergence = (
        $provisional.status -eq "not_qualified" -and
        $comparisons.Count -eq 1 -and
        $comparisons[0].mandatory_convergence_pass -eq $false -and
        $failures.Count -eq 1 -and
        $failures[0] -eq $expectedFailure
    )
    if (-not $measuredNonconvergence) {
        throw (
            "Funnel $Name failed for a reason other than measured M120->M160 " +
            "nonconvergence; conditional M240 is prohibited."
        )
    }

    $m160Sha256 = Get-FileSha256 -Path $m160Funnel
    $m240Root = Join-Path $root "m240"
    $m240Summary = Join-Path $m240Root "watchdog_summary.json"
    Invoke-Task033Watchdog `
        -StepName "hybrid_${Category}_${Name}_m240_conditional" `
        -Target "hybrid" `
        -Degree $Degree `
        -HNm $HNm `
        -MpiSize 4 `
        -RequestedModes 240 `
        -CandidateModes 240 `
        -SummaryOutput $m240Summary `
        -AttemptRoot (Join-Path $m240Root "attempts") `
        -SolverPath "modal-schur-memory-minimal" `
        -BottomInterfaceNm $BottomInterfaceNm `
        -TopInterfaceNm $TopInterfaceNm `
        -GradedReferenceH $GradedReferenceH `
        -M160FunnelEvidence $m160Funnel `
        -M160FunnelSha256 $m160Sha256 `
        -TimeoutSeconds $HybridTimeoutSeconds

    $qualifiedFunnel = Join-Path $root "funnel_m80_m120_m160_m240.json"
    $finalCommand = @(
        "python", "-m", "benchmarks.run_task033_hybrid_funnel"
    )
    foreach ($summary in @($summaries + $m240Summary)) {
        $finalCommand += Convert-ToContainerPath -HostPath $summary
    }
    $finalCommand += @(
        "--output", (Convert-ToContainerPath -HostPath $qualifiedFunnel),
        "--require-qualified"
    )
    Invoke-DockerFileStep `
        -StepName "hybrid_${Category}_${Name}_aggregate_m240" `
        -ContainerCommand $finalCommand `
        -Outputs @($qualifiedFunnel)
    return $qualifiedFunnel
}

function Invoke-HybridComparisonAnchor {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][int]$Degree
    )

    $root = Join-Path $ArtifactRootHost "hybrid/anchors/$Name"
    $summary = Join-Path $root "watchdog_summary.json"
    Invoke-Task033Watchdog `
        -StepName "hybrid_anchor_${Name}_augmented_vs_minimal" `
        -Target "hybrid" `
        -Degree $Degree `
        -HNm "5.0" `
        -MpiSize 4 `
        -RequestedModes 160 `
        -CandidateModes 160 `
        -SummaryOutput $summary `
        -AttemptRoot (Join-Path $root "attempts") `
        -SolverPath "augmented" `
        -BottomInterfaceNm "10.0" `
        -TopInterfaceNm "110.0" `
        -CompareModalSchur `
        -TimeoutSeconds $HybridTimeoutSeconds
    return $summary
}

# Phase 0: immutable source/image/resource identity.
$CommitSha = Get-FormalSourceSha
$artifactRelative = Convert-ToRepoRelativePath -HostPath $ArtifactRootHost
$ignoreCheck = Invoke-GitCapture -ArgumentList @(
    "check-ignore", "--quiet", "--no-index", "--", $artifactRelative
)
if ($ignoreCheck.ExitCode -ne 0) {
    throw "Campaign artifact root is not ignored by Git: $artifactRelative"
}
[IO.Directory]::CreateDirectory($ArtifactRootHost) | Out-Null

$imageInspect = Invoke-NativeCapture `
    -FilePath $DockerExecutable `
    -ArgumentList @("image", "inspect", $DockerImage)
if ($imageInspect.ExitCode -ne 0) {
    throw "docker image inspect failed for $DockerImage."
}
$imageItems = @($imageInspect.Text | ConvertFrom-Json)
if ($imageItems.Count -ne 1) {
    throw "Expected exactly one Docker image inspection record."
}
$ImageDigest = "$($imageItems[0].Id)".ToLowerInvariant()
if ($ImageDigest -notmatch '^sha256:[0-9a-f]{64}$') {
    throw "Docker image lacks an immutable sha256 image digest."
}
if ($ImageDigest -ne $ExpectedImageDigest) {
    throw (
        "Task033 requires the reviewed Docker image digest " +
        "$ExpectedImageDigest, observed $ImageDigest."
    )
}
$DockerRepoDigests = @()
if ($imageItems[0].PSObject.Properties.Name -contains "RepoDigests") {
    $DockerRepoDigests = @($imageItems[0].RepoDigests)
}

# Formal aggregation is read-only but requires Draft 2020-12 JSON Schema.
# The locked numerical image intentionally does not carry that package, so
# fail before any expensive PDE if the declared host aggregation runtime is
# unavailable or cannot import this checkout.
$hostPreflightCode = @'
import json
import sys
import jsonschema
from importlib.metadata import version
import benchmarks.task033_formal_records
import benchmarks.task033_equal_accuracy
print(json.dumps({
    'python_executable': sys.executable,
    'python_version': sys.version.split()[0],
    'jsonschema_version': version('jsonschema'),
}, sort_keys=True))
'@
Push-Location $RepoRoot
try {
    $hostPreflight = Invoke-NativeCapture `
        -FilePath $HostPythonExecutable `
        -ArgumentList @("-c", $hostPreflightCode)
} finally {
    Pop-Location
}
if ($hostPreflight.ExitCode -ne 0) {
    throw "Host formal-aggregation runtime preflight failed."
}
$HostAggregationRuntime = $hostPreflight.Text | ConvertFrom-Json

$preflightPath = Join-Path $ArtifactRootHost "phase_00_preflight.json"
if (-not (Test-StepComplete -StepName "phase_00_preflight" -Outputs @($preflightPath))) {
    $preflightCode = @'
from pathlib import Path
import json

memory_max = int(Path('/sys/fs/cgroup/memory.max').read_text().strip())
swap_max = int(Path('/sys/fs/cgroup/memory.swap.max').read_text().strip())
swap_current = int(Path('/sys/fs/cgroup/memory.swap.current').read_text().strip())
payload = {
    'memory_max_bytes': memory_max,
    'memory_swap_max_bytes': swap_max,
    'memory_swap_current_bytes': swap_current,
}
print(json.dumps(payload, sort_keys=True))
raise SystemExit(
    0 if memory_max == 13958643712 and swap_max == 0 and swap_current == 0 else 2
)
'@
    $preflightArgs = Get-DockerRunArguments -ContainerCommand @(
        "python", "-c", $preflightCode
    )
    $preflightResult = Invoke-NativeCapture `
        -FilePath $DockerExecutable `
        -ArgumentList $preflightArgs
    if ($preflightResult.ExitCode -ne 0) {
        throw "13g/no-swap Docker cgroup preflight failed."
    }
    $cgroup = $preflightResult.Text | ConvertFrom-Json
    if (
        $cgroup.memory_max_bytes -ne $ExpectedMemoryMaxBytes -or
        $cgroup.memory_swap_max_bytes -ne 0 -or
        $cgroup.memory_swap_current_bytes -ne 0
    ) {
        throw "Docker cgroup authority is not exactly 13g with swap disabled."
    }
    $preflightRecord = [ordered]@{
        schema_version = "task033.formal-campaign-preflight.v1"
        source_commit_full_sha = $CommitSha
        complete_nonignored_worktree_clean = $true
        docker_image = $DockerImage
        docker_image_digest = $ImageDigest
        docker_repo_digests = $DockerRepoDigests
        host_aggregation_runtime = $HostAggregationRuntime
        cgroup = $cgroup
        warning_gib = [double]$WarningGiB
        controlled_termination_gib = [double]$TerminateGiB
        one_large_case_at_a_time = $true
    }
    Write-Utf8NoBom `
        -Path $preflightPath `
        -Text (($preflightRecord | ConvertTo-Json -Depth 8) + "`n")
    Complete-Step `
        -StepName "phase_00_preflight" `
        -Outputs @($preflightPath) `
        -ExitCode $preflightResult.ExitCode
}

# FileShare.None prevents two campaign processes from launching large cases.
$lockPath = Join-Path $ArtifactRootHost "task033_formal_campaign.lock"
$campaignLock = $null
try {
    $campaignLock = [IO.File]::Open(
        $lockPath,
        [IO.FileMode]::OpenOrCreate,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::None
    )

    # Phase 1: Case090 real MPI1/MPI2/MPI4 shards under the external watchdog.
    $case090Root = Join-Path $ArtifactRootHost "case090"
    $case090Shards = @()
    $case090Watchdogs = @()
    foreach ($mpiSize in @(1, 2, 4)) {
        $mpiRoot = Join-Path $case090Root "mpi$mpiSize"
        [IO.Directory]::CreateDirectory($mpiRoot) | Out-Null
        $shard = Join-Path $mpiRoot "shard.json"
        $raw = Join-Path $mpiRoot "watchdog_samples.jsonl"
        $watchdog = Join-Path $mpiRoot "watchdog_summary.json"
        $case090Shards += $shard
        $case090Watchdogs += $watchdog
        $command = @(
            "python", "-m", "benchmarks.run_task033_case090_watchdog",
            "--mpi-size", "$mpiSize",
            "--raw-output", (Convert-ToContainerPath -HostPath $raw),
            "--summary-output", (Convert-ToContainerPath -HostPath $watchdog),
            "--sample-interval", "1.0",
            "--wall-timeout-seconds", "$Case090TimeoutSeconds",
            "--termination-grace-seconds", "10.0",
            "--",
            "mpiexec", "-n", "$mpiSize",
            "python", "-m", "benchmarks.run_task033_case090_pde_core",
            "shard",
            "--output", (Convert-ToContainerPath -HostPath $shard),
            "--work-dir", (Convert-ToContainerPath -HostPath (Join-Path $mpiRoot "work"))
        )
        Invoke-DockerFileStep `
            -StepName "case090_mpi${mpiSize}_external_watchdog" `
            -ContainerCommand $command `
            -Outputs @($watchdog, $shard, $raw)
    }
    $Case090Aggregate = Join-Path $case090Root "case090_core_aggregate.json"
    $case090AggregateCommand = @(
        "python", "-m", "benchmarks.run_task033_case090_pde_core",
        "aggregate"
    )
    foreach ($shard in $case090Shards) {
        $case090AggregateCommand += Convert-ToContainerPath -HostPath $shard
    }
    $case090AggregateCommand += "--memory-summaries"
    foreach ($watchdog in $case090Watchdogs) {
        $case090AggregateCommand += Convert-ToContainerPath -HostPath $watchdog
    }
    $case090AggregateCommand += @(
        "--output", (Convert-ToContainerPath -HostPath $Case090Aggregate),
        "--require-pass"
    )
    Invoke-DockerFileStep `
        -StepName "case090_mpi1_mpi2_mpi4_aggregate" `
        -ContainerCommand $case090AggregateCommand `
        -Outputs @($Case090Aggregate)
    $Case090AggregateSha256 = Get-FileSha256 -Path $Case090Aggregate

    # Phase 2: the formal 36-shard MPI1 QEP matrix plus explicit MPI2/MPI4
    # timeout-only negatives.  Negatives are never supplied to the aggregate.
    $QepMaterials = @("air", "lossy_homogeneous", "stage4_xy")
    $Degrees = @(1, 2, 3, 4)
    $QepHLevels = @(
        [pscustomobject]@{ Value = "5.0"; Label = "h5" },
        [pscustomobject]@{ Value = "3.0"; Label = "h3" },
        [pscustomobject]@{ Value = "2.5"; Label = "h2p5" }
    )
    $QepNegativeMpiSizes = @(2, 4)
    $qepPassSummaries = @()
    foreach ($material in $QepMaterials) {
        foreach ($degree in $Degrees) {
            foreach ($hLevel in $QepHLevels) {
                $slug = "${material}_p${degree}_$($hLevel.Label)"
                $passRoot = Join-Path $ArtifactRootHost "qep/mpi1/$slug"
                $passSummary = Join-Path $passRoot "watchdog_summary.json"
                $qepPassSummaries += $passSummary
                Invoke-Task033Watchdog `
                    -StepName "qep_${slug}_mpi1" `
                    -Target "qep" `
                    -Degree $degree `
                    -HNm $hLevel.Value `
                    -MpiSize 1 `
                    -RequestedModes 8 `
                    -CandidateModes 8 `
                    -SummaryOutput $passSummary `
                    -AttemptRoot (Join-Path $passRoot "attempts") `
                    -MaterialKind $material `
                    -TimeoutSeconds $QepTimeoutSeconds

            }
        }
    }
    # MPI2/MPI4 are bounded timeout-only negatives for the known distributed
    # PEP/MUMPS boundary, not another 72-member physical matrix.  One fixed
    # patterned p2/h3 case per communicator is sufficient and keeps the
    # negative evidence distinct from the qualified MPI1 aggregate.
    foreach ($negativeMpi in $QepNegativeMpiSizes) {
        $slug = "stage4_xy_p2_h3"
        $negativeRoot = Join-Path $ArtifactRootHost (
            "qep/timeout_negatives/mpi${negativeMpi}/$slug"
        )
        $negativeSummary = Join-Path $negativeRoot "watchdog_summary.json"
        Invoke-Task033Watchdog `
            -StepName "qep_${slug}_mpi${negativeMpi}_timeout_negative" `
            -Target "qep" `
            -Degree 2 `
            -HNm "3.0" `
            -MpiSize $negativeMpi `
            -RequestedModes 8 `
            -CandidateModes 8 `
            -SummaryOutput $negativeSummary `
            -AttemptRoot (Join-Path $negativeRoot "attempts") `
            -MaterialKind "stage4_xy" `
            -TimeoutSeconds $QepNegativeTimeoutSeconds `
            -ExpectedTimeoutNegative
    }

    # Phase 3: all nine safe uniform rows, one serial M80/M120/M160 funnel each.
    $safeUniform = @(
        [pscustomobject]@{ Key = "p1_h5"; Degree = 1; H = "5.0" },
        [pscustomobject]@{ Key = "p1_h3"; Degree = 1; H = "3.0" },
        [pscustomobject]@{ Key = "p1_h2p5"; Degree = 1; H = "2.5" },
        [pscustomobject]@{ Key = "p1_h2"; Degree = 1; H = "2.0" },
        [pscustomobject]@{ Key = "p1_h1p5"; Degree = 1; H = "1.5" },
        [pscustomobject]@{ Key = "p2_h5"; Degree = 2; H = "5.0" },
        [pscustomobject]@{ Key = "p2_h3"; Degree = 2; H = "3.0" },
        [pscustomobject]@{ Key = "p2_h2p5"; Degree = 2; H = "2.5" },
        [pscustomobject]@{ Key = "p3_h5"; Degree = 3; H = "5.0" }
    )
    $uniformFunnels = @{}
    foreach ($entry in $safeUniform) {
        $requalify = $entry.Key -eq "p2_h3"
        $uniformFunnels[$entry.Key] = Invoke-HybridFunnel `
            -Name $entry.Key `
            -Category "uniform" `
            -Degree $entry.Degree `
            -HNm $entry.H `
            -AnchorRequalification:$requalify
    }

    # Task033 8.3 anchors: augmented primary versus the memory-minimal Schur
    # comparison.  Never rely on the inherited fast comparison default.
    $p1Anchor = Invoke-HybridComparisonAnchor -Name "p1_h5" -Degree 1
    $p3Anchor = Invoke-HybridComparisonAnchor -Name "p3_h5" -Degree 3
    Write-Host "comparison anchors: $p1Anchor ; $p3Anchor"

    # Phase 4: graded p2/h5 and p2/h3 funnels.
    $gradedFunnels = @{}
    foreach ($graded in @(
        [pscustomobject]@{ Key = "p2_h5_graded"; H = "5.0" },
        [pscustomobject]@{ Key = "p2_h3_graded"; H = "3.0" }
    )) {
        $gradedFunnels[$graded.Key] = Invoke-HybridFunnel `
            -Name $graded.Key `
            -Category "graded" `
            -Degree 2 `
            -HNm $graded.H `
            -GradedReferenceH $graded.H
    }

    # Phase 5: buffer 10 reuses the same-SHA uniform p2/h3 funnel.  Only the
    # three altered buffers are launched.
    $bufferFunnels = @{
        "buffer_10" = $uniformFunnels["p2_h3"]
    }
    foreach ($buffer in @(
        [pscustomobject]@{
            Key = "buffer_7p5"; Bottom = "7.5"; Top = "112.5"
        },
        [pscustomobject]@{
            Key = "buffer_5"; Bottom = "5.0"; Top = "115.0"
        },
        [pscustomobject]@{
            Key = "buffer_2p5"; Bottom = "2.5"; Top = "117.5"
        }
    )) {
        $bufferFunnels[$buffer.Key] = Invoke-HybridFunnel `
            -Name $buffer.Key `
            -Category "buffer" `
            -Degree 2 `
            -HNm "3.0" `
            -BottomInterfaceNm $buffer.Bottom `
            -TopInterfaceNm $buffer.Top
    }

    # Phase 6: read-only primary formal aggregation.
    $aggregateRoot = Join-Path $ArtifactRootHost "aggregates"
    [IO.Directory]::CreateDirectory($aggregateRoot) | Out-Null

    $qepAggregate = Join-Path $aggregateRoot "qep_order_study.json"
    $qepAggregateCommand = @(
        "-m", "benchmarks.run_task033_formal_records",
        "qep-order-study", "--mpi-size", "1"
    )
    foreach ($summary in $qepPassSummaries) {
        $qepAggregateCommand += $summary
    }
    Invoke-HostJsonCaptureStep `
        -StepName "aggregate_qep_order_study" `
        -PythonArguments $qepAggregateCommand `
        -Output $qepAggregate

    $uniformAggregate = Join-Path $aggregateRoot "uniform_matrix.json"
    $uniformAggregateCommand = @(
        "-m", "benchmarks.run_task033_formal_records",
        "uniform-matrix",
        "--resource-matrix",
        (Join-Path $RepoRoot "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/resource_matrix.json")
    )
    foreach ($entry in $safeUniform) {
        if ($entry.Key -ne "p2_h3") {
            $binding = "$($entry.Key)=$($uniformFunnels[$entry.Key])"
            $uniformAggregateCommand += @("--funnel", $binding)
        }
    }
    $p2H3SelectedWatchdog = Join-Path $ArtifactRootHost (
        "hybrid/uniform/p2_h3/m160/watchdog_summary.json"
    )
    $uniformAggregateCommand += @(
        "--watchdog",
        "p2_h3=$p2H3SelectedWatchdog"
    )
    Invoke-HostJsonCaptureStep `
        -StepName "aggregate_uniform_matrix" `
        -PythonArguments $uniformAggregateCommand `
        -Output $uniformAggregate

    $adaptiveH5 = Join-Path $aggregateRoot "adaptive_p2_h5.json"
    Invoke-HostJsonCaptureStep `
        -StepName "aggregate_adaptive_p2_h5" `
        -PythonArguments @(
            "-m", "benchmarks.run_task033_formal_records",
            "adaptive",
            "--graded-plan",
            (Join-Path $RepoRoot "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/adaptive_p2_h5_plan.json"),
            "--reference-evidence",
            $uniformFunnels["p2_h5"],
            "--candidate-evidence",
            $gradedFunnels["p2_h5_graded"]
        ) `
        -Output $adaptiveH5

    $adaptiveH3 = Join-Path $aggregateRoot "adaptive_p2_h3.json"
    Invoke-HostJsonCaptureStep `
        -StepName "aggregate_adaptive_p2_h3" `
        -PythonArguments @(
            "-m", "benchmarks.run_task033_formal_records",
            "adaptive",
            "--graded-plan",
            (Join-Path $RepoRoot "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/adaptive_p2_h3_plan.json"),
            "--reference-evidence",
            $uniformFunnels["p2_h3"],
            "--candidate-evidence",
            $gradedFunnels["p2_h3_graded"]
        ) `
        -Output $adaptiveH3

    $bufferAggregate = Join-Path $aggregateRoot "buffer_tradeoff.json"
    Invoke-HostJsonCaptureStep `
        -StepName "aggregate_buffer_tradeoff" `
        -PythonArguments @(
            "-m", "benchmarks.run_task033_formal_records",
            "buffer-tradeoff",
            $bufferFunnels["buffer_10"],
            $bufferFunnels["buffer_7p5"],
            $bufferFunnels["buffer_5"],
            $bufferFunnels["buffer_2p5"]
        ) `
        -Output $bufferAggregate

    $equalAccuracy = Join-Path $aggregateRoot "equal_accuracy.json"
    $equalAccuracyCommand = @(
        "-m", "benchmarks.run_task033_equal_accuracy",
        "--reference",
        $uniformFunnels["p2_h3"],
        "--output", $equalAccuracy
    )
    foreach ($entry in $safeUniform) {
        if ($entry.Key -ne "p2_h3") {
            $equalAccuracyCommand += @(
                "--candidate",
                $uniformFunnels[$entry.Key]
            )
        }
    }
    Invoke-HostFileStep `
        -StepName "aggregate_equal_accuracy" `
        -PythonArguments $equalAccuracyCommand `
        -Outputs @($equalAccuracy)

    # Variable-p has no evidence-selection ambiguity, so produce its formal
    # fail-closed capability audit on the same clean SHA now.  Only the 1 TiB
    # projection waits for review of the two measured adaptive records.
    $variableP = Join-Path $aggregateRoot "variable_p_capability_audit.json"
    Invoke-DockerFileStep `
        -StepName "aggregate_variable_p_capability_audit" `
        -ContainerCommand @(
            "python", "-m", "benchmarks.run_task033_variable_p_audit",
            "--formal", "--repo-root", "/work",
            "--output", (Convert-ToContainerPath -HostPath $variableP)
        ) `
        -Outputs @($variableP)

    # Phase 7 is deliberately explicit but deferred.  It must run only after
    # reviewing which measured adaptive record is the approved compression
    # evidence; no raw CLI compression number may be promoted automatically.
    $followUpPath = Join-Path $aggregateRoot "phase_07_follow_up_aggregation.json"
    if (-not (
        Test-StepComplete `
            -StepName "phase_07_follow_up_aggregation_plan" `
            -Outputs @($followUpPath)
    )) {
        $followUp = [ordered]@{
            schema_version = "task033.follow-up-aggregation-plan.v1"
            status = "one_tib_deferred_pending_reviewed_measured_compression_evidence"
            source_commit_full_sha = $CommitSha
            phase = "one_tib_projection"
            dependencies = @(
                Convert-ToRepoRelativePath -HostPath $adaptiveH5
                Convert-ToRepoRelativePath -HostPath $adaptiveH3
                Convert-ToRepoRelativePath -HostPath $bufferAggregate
                Convert-ToRepoRelativePath -HostPath $equalAccuracy
                Convert-ToRepoRelativePath -HostPath $variableP
            )
            one_tib_command_template = @(
                "python", "-m", "benchmarks.run_task033_one_tib_projection",
                "--compression-evidence", "<reviewed-adaptive-formal-json>",
                "--formal", "--repo-root", "/work"
            )
            prohibition = (
                "Do not classify 1 TiB from a raw --measured-compression value; " +
                "bind one reviewed same-accuracy adaptive formal JSON."
            )
        }
        Write-Utf8NoBom `
            -Path $followUpPath `
            -Text (($followUp | ConvertTo-Json -Depth 8) + "`n")
        Complete-Step `
            -StepName "phase_07_follow_up_aggregation_plan" `
            -Outputs @($followUpPath) `
            -ExitCode 0
    }

    Assert-FormalSourceStable -ExpectedSha $CommitSha
    Write-Host "Task033 formal measurements and primary aggregates completed."
    Write-Host "Only 1 TiB remains the explicit reviewed-evidence follow-up phase."
} finally {
    if ($null -ne $campaignLock) {
        $campaignLock.Dispose()
    }
}
