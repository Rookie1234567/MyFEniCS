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
$ExpectedRuntimeGuardBytes = 12884901888
$ExpectedImageDigest = (
    "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d"
)
$RuntimeGuardBudgetGiB = 12.0
$WarningGiB = "9.857142857142856"
$TerminateGiB = "11.142857142857142"
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

function Get-TextSha256 {
    param([Parameter(Mandatory = $true)][string]$Text)

    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString(
            $algorithm.ComputeHash($bytes)
        )).Replace("-", "").ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
    }
}

function Get-StepMarkerPath {
    param([Parameter(Mandatory = $true)][string]$PrimaryOutput)

    # Keep marker paths independent of deeply nested output paths.  Windows
    # PowerShell 5.1/.NET can fail at the legacy MAX_PATH boundary even when
    # the parent directory exists (the timeout-negative marker reached exactly
    # 260 characters once the atomic-write suffix was appended).
    $relativeOutput = Convert-ToRepoRelativePath -HostPath $PrimaryOutput
    $outputKey = (Get-TextSha256 -Text $relativeOutput).Substring(0, 24)
    $markerRoot = Join-Path $ArtifactRootHost "_step_markers"
    $sourceKey = $CommitSha.Substring(0, 12)
    return Join-Path $markerRoot "$sourceKey-$outputKey.json"
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

function Convert-ToNativeExitCode {
    param([Parameter(Mandatory = $true)][int]$Code)

    # POSIX subprocesses report signal termination as a negative return code
    # (for example SIGTERM as -15), while Docker/PowerShell exposes the same
    # container result as the unsigned 8-bit process exit code (241).
    return (($Code % 256) + 256) % 256
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
        # The bind-mounted checkout is produced by Windows Git with CRLF
        # working-tree files.  Inject the matching normalization policy into
        # every *container process* so Linux Git checks content rather than
        # reporting the whole checkout dirty from line-ending presentation.
        # Host Git still performs the first complete nonignored clean gate.
        "--env", "GIT_CONFIG_COUNT=1",
        "--env", "GIT_CONFIG_KEY_0=core.autocrlf",
        "--env", "GIT_CONFIG_VALUE_0=true",
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
        $summary = Get-Content -Raw -LiteralPath $SummaryOutput | ConvertFrom-Json
        $marker = Get-Content -Raw -LiteralPath (
            Get-StepMarkerPath -PrimaryOutput $SummaryOutput
        ) | ConvertFrom-Json
        $normalizedSummaryExit = Convert-ToNativeExitCode `
            -Code ([int]$summary.return_code)
        $validResume = (
            $summary.status -eq "formal_not_pass" -and
            $summary.formal_pass -eq $false -and
            $summary.numeric_pass -eq $false -and
            $summary.return_code -ne 0 -and
            $summary.terminated_for_timeout -eq $true -and
            $summary.terminated_for_memory -eq $false -and
            $summary.terminated_for_authority_unreadable -eq $false -and
            $summary.memory_authority_pass -eq $true -and
            $summary.no_swap -eq $true -and
            $summary.resource_authority.gate.pass -eq $true -and
            $summary.source_gate.pass -eq $true -and
            $summary.launch_gate.pass -eq $true -and
            $marker.native_exit_code -eq $normalizedSummaryExit
        )
        if (-not $validResume) {
            throw "Timeout-negative resume marker is not bound to its summary."
        }
        return
    }
    Assert-FormalSourceStable -ExpectedSha $CommitSha
    if (Test-Path -LiteralPath $SummaryOutput -PathType Leaf) {
        Remove-Item -LiteralPath $SummaryOutput -Force
    }
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
    $normalizedSummaryExit = Convert-ToNativeExitCode `
        -Code ([int]$summary.return_code)
    $validTimeoutNegative = (
        $summary.status -eq "formal_not_pass" -and
        $summary.formal_pass -eq $false -and
        $summary.numeric_pass -eq $false -and
        $summary.return_code -ne 0 -and
        $normalizedSummaryExit -eq $exitCode -and
        $summary.terminated_for_timeout -eq $true -and
        $summary.terminated_for_memory -eq $false -and
        $summary.terminated_for_authority_unreadable -eq $false -and
        $summary.memory_authority_pass -eq $true -and
        $summary.no_swap -eq $true -and
        $summary.resource_authority.gate.pass -eq $true -and
        $summary.source_gate.pass -eq $true -and
        $summary.launch_gate.pass -eq $true
    )
    if (-not $validTimeoutNegative) {
        throw "Step $StepName was not the required clean timeout-only negative."
    }
    Complete-Step -StepName $StepName -Outputs $outputs -ExitCode $exitCode
}

function Get-Task033CommandValue {
    param(
        [Parameter(Mandatory = $true)][object[]]$Command,
        [Parameter(Mandatory = $true)][string]$Option
    )

    for ($index = 0; $index -lt $Command.Count - 1; $index++) {
        if ([string]$Command[$index] -eq $Option) {
            return [string]$Command[$index + 1]
        }
    }
    return $null
}

function Get-QepP4SolverRecord {
    param([Parameter(Mandatory = $true)][psobject]$Summary)

    if (
        $null -eq $Summary.solver_record_ignored_path -or
        [string]::IsNullOrWhiteSpace(
            [string]$Summary.solver_record_ignored_path
        ) -or
        [string]$Summary.solver_record_sha256 -notmatch '^[0-9a-f]{64}$'
    ) {
        throw "p4 QEP watchdog has no complete solver-record descriptor."
    }
    $rawPath = [string]$Summary.solver_record_ignored_path
    $solverPath = if ([IO.Path]::IsPathRooted($rawPath)) {
        [IO.Path]::GetFullPath($rawPath)
    } else {
        [IO.Path]::GetFullPath((Join-Path $RepoRoot $rawPath))
    }
    $repoPrefix = $RepoRoot + [IO.Path]::DirectorySeparatorChar
    if (-not $solverPath.StartsWith(
        $repoPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "p4 QEP solver record escapes the repository: $solverPath"
    }
    if (-not (Test-Path -LiteralPath $solverPath -PathType Leaf)) {
        throw "p4 QEP watchdog solver record is missing: $solverPath"
    }
    $observedSha = Get-FileSha256 -Path $solverPath
    if ($observedSha -ne ([string]$Summary.solver_record_sha256).ToLowerInvariant()) {
        throw "p4 QEP solver-record SHA256 does not match its watchdog."
    }
    $record = Get-Content -Raw -LiteralPath $solverPath | ConvertFrom-Json
    $embedded = $Summary.measurements | ConvertTo-Json -Depth 100 -Compress
    $preserved = $record | ConvertTo-Json -Depth 100 -Compress
    if ($embedded -ne $preserved) {
        throw "p4 QEP embedded measurements differ from the solver record."
    }
    return $record
}

function Assert-QepP4ControlledOutcome {
    param(
        [Parameter(Mandatory = $true)][string]$SummaryOutput,
        [Parameter(Mandatory = $true)][string]$MaterialKind,
        [Parameter(Mandatory = $true)][string]$HNm,
        [Parameter(Mandatory = $true)][string]$AttemptRoot
    )

    if (-not (Test-Path -LiteralPath $SummaryOutput -PathType Leaf)) {
        throw "p4 QEP step produced no watchdog summary."
    }
    $summary = Get-Content -Raw -LiteralPath $SummaryOutput | ConvertFrom-Json
    $rawSolverPath = [string]$summary.solver_record_ignored_path
    $solverPath = if ([IO.Path]::IsPathRooted($rawSolverPath)) {
        [IO.Path]::GetFullPath($rawSolverPath)
    } else {
        [IO.Path]::GetFullPath((Join-Path $RepoRoot $rawSolverPath))
    }
    $attemptPrefix = [IO.Path]::GetFullPath($AttemptRoot).TrimEnd(
        [char[]]@(47, 92)
    ) + [IO.Path]::DirectorySeparatorChar
    if (-not $solverPath.StartsWith(
        $attemptPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "p4 QEP solver record is not bound to this step attempt root."
    }
    $record = Get-QepP4SolverRecord -Summary $summary
    $command = @($summary.command)
    # Keep each comparison in a named hashtable entry.  In PowerShell, comma
    # has higher precedence than comparison operators inside @(...), so an
    # unparenthesized comma-separated comparison list can collapse to one
    # false Boolean instead of an array of independent checks.
    $commonChecks = [ordered]@{
        schema_version = (
            $summary.schema_version -eq "task033.memory-watchdog.v2"
        )
        benchmark_id = (
            $summary.benchmark_id -eq "task033_external_memory_watchdog"
        )
        target = ($summary.target -eq "qep")
        requested_modes = ($summary.requested_modes -eq 8)
        candidate_modes = ($summary.candidate_modes -eq 16)
        command_requested_modes = (
            (Get-Task033CommandValue `
                -Command $command `
                -Option "--requested-modes") -eq "8"
        )
        command_left_candidate_modes = (
            (Get-Task033CommandValue `
                -Command $command `
                -Option "--left-candidate-modes") -eq "16"
        )
        memory_authority_pass = ($summary.memory_authority_pass -eq $true)
        no_swap = ($summary.no_swap -eq $true)
        not_terminated_for_memory = (
            $summary.terminated_for_memory -eq $false
        )
        not_terminated_for_timeout = (
            $summary.terminated_for_timeout -eq $false
        )
        authority_readable = (
            $summary.terminated_for_authority_unreadable -eq $false
        )
        resource_gate = ($summary.resource_authority.gate.pass -eq $true)
        source_gate = ($summary.source_gate.pass -eq $true)
        launch_gate = ($summary.launch_gate.pass -eq $true)
        material_kind = (
            $record.candidate.material_kind -eq $MaterialKind
        )
        degree = ($record.candidate.degree -eq 4)
        h_nm = ($record.candidate.h_nm -eq [double]$HNm)
        mpi_size = ($record.candidate.mpi_size -eq 1)
    }
    $failedCommonChecks = @(
        $commonChecks.GetEnumerator() |
            Where-Object { $_.Value -ne $true } |
            ForEach-Object { $_.Key }
    )
    if ($failedCommonChecks.Count -ne 0) {
        throw (
            "p4 QEP outcome failed source/resource/launch/identity checks: " +
            ($failedCommonChecks -join ", ")
        )
    }

    if ($summary.status -eq "measured_shard_pass") {
        Assert-WatchdogPass -Outputs @($SummaryOutput)
        if ($record.status -ne "measured_shard_pass") {
            throw "p4 QEP pass summary does not embed a passing solver record."
        }
        return $summary
    }

    if (
        $summary.status -ne "formal_not_pass" -or
        $summary.formal_pass -ne $false -or
        $summary.numeric_pass -ne $false -or
        $summary.return_code -ne 2 -or
        $record.status -ne "measured_shard_failed" -or
        $record.identity.is_pde_run -ne $true -or
        $record.identity.is_solver_pass -ne $false -or
        $record.identity.is_physical_qualification_record -ne $false -or
        $record.identity.physical_qualified -ne $false -or
        $record.runtime_preflight.runtime_contract_verified -ne $true -or
        $record.runtime_preflight.launch_eligible -ne $true -or
        @($record.runtime_preflight.failures).Count -ne 0 -or
        $record.gates.all_required_numerical_gates_pass -ne $false
    ) {
        throw "p4 QEP nonzero result is not a complete measured shard failure."
    }
    $failureProperty = $record.PSObject.Properties["failure"]
    if ($null -ne $failureProperty -and $null -ne $failureProperty.Value) {
        throw "p4 QEP exception failure payload is not a controlled negative."
    }

    $classification = $record.numerical_results.left_right_classification
    if (
        $classification.left_candidate_pool_policy -ne (
            "max_requested_plus_8_or_2x"
        ) -or
        $classification.right_requested_modes -ne 8 -or
        $classification.left_candidate_requested_modes -ne 16 -or
        $classification.left_candidate_converged_modes -lt 8
    ) {
        throw "p4 QEP negative violates the audited 8-to-16 candidate pool."
    }
    $pairErrors = @($classification.left_pair_relative_errors)
    if ($pairErrors.Count -ne 8) {
        throw "p4 QEP negative lacks eight raw left/right pair errors."
    }
    $pairMaximum = 0.0
    foreach ($rawError in $pairErrors) {
        $errorValue = [double]$rawError
        if (
            [double]::IsNaN($errorValue) -or
            [double]::IsInfinity($errorValue) -or
            $errorValue -lt 0.0
        ) {
            throw "p4 QEP negative contains a non-finite pair error."
        }
        $pairMaximum = [Math]::Max($pairMaximum, $errorValue)
    }
    $recordedPairMaximum = [double]$classification.left_pair_relative_error_max
    $pairScale = [Math]::Max([Math]::Abs($pairMaximum), 1.0e-15)
    if (
        [Math]::Abs($recordedPairMaximum - $pairMaximum) `
            -gt 1.0e-12 * $pairScale
    ) {
        throw "p4 QEP negative pair-error maximum disagrees with its raw list."
    }

    $recomputed = [ordered]@{
        "polynomial_relative_residual_le_1e-10" = (
            [double]$classification.right_polynomial_relative_residual_max `
                -le 1.0e-10
        )
        "left_polynomial_relative_residual_le_1e-8" = (
            [double]$classification.left_polynomial_relative_residual_max `
                -le 1.0e-8
        )
        "biorthogonality_identity_error_le_1e-6" = (
            [double]$classification.biorthogonality_identity_error `
                -le 1.0e-6
        )
        "left_right_beta_pair_relative_error_le_1e-7" = (
            [double]$classification.left_pair_relative_error_max `
                -le 1.0e-7
        )
    }
    $controlledFailures = @()
    foreach ($name in $recomputed.Keys) {
        $property = $record.gates.PSObject.Properties[$name]
        if (
            $null -eq $property -or
            $property.Value -isnot [bool] -or
            $property.Value -ne $recomputed[$name]
        ) {
            throw "p4 QEP numerical Gate $name is absent or inconsistent."
        }
        if ($property.Value -eq $false) {
            $controlledFailures += $name
        }
    }
    if ($controlledFailures.Count -eq 0) {
        throw "p4 QEP measured failure has no controlled numerical Gate failure."
    }
    $requiredTrueGates = @(
        "converged_eigenpair",
        "no_swap",
        "below_controlled_termination",
        "formal_resource_authority_pass",
        "raised_quadrature_pass",
        "patterned_tracking_compact_ready",
        "single_shard_only_not_physical_qualification",
        "source_identity_stable_clean_pass"
    )
    foreach ($name in $requiredTrueGates) {
        $property = $record.gates.PSObject.Properties[$name]
        if ($null -eq $property -or $property.Value -ne $true) {
            throw "p4 QEP negative failed non-whitelisted Gate $name."
        }
    }
    $analyticExpected = if ($MaterialKind -eq "stage4_xy") {
        "not_applicable_patterned_cross_section"
    } else {
        $true
    }
    if ($record.gates.analytic_beta_error_finite -ne $analyticExpected) {
        throw "p4 QEP negative failed the analytic identity Gate."
    }
    if (
        $record.numerical_results.quadrature.raised_comparison.failure -ne $null -or
        $record.numerical_results.cross_h_tracking.failure -ne $null
    ) {
        throw "p4 QEP exception-derived failure is not a controlled negative."
    }
    return $summary
}

function Invoke-DockerQepP4Step {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][string[]]$ContainerCommand,
        [Parameter(Mandatory = $true)][string]$SummaryOutput,
        [Parameter(Mandatory = $true)][string]$MaterialKind,
        [Parameter(Mandatory = $true)][string]$HNm,
        [Parameter(Mandatory = $true)][string]$AttemptRoot
    )

    $outputs = @($SummaryOutput)
    if (Test-StepComplete -StepName $StepName -Outputs $outputs) {
        $summary = Assert-QepP4ControlledOutcome `
            -SummaryOutput $SummaryOutput `
            -MaterialKind $MaterialKind `
            -HNm $HNm `
            -AttemptRoot $AttemptRoot
        $marker = Get-Content -Raw -LiteralPath (
            Get-StepMarkerPath -PrimaryOutput $SummaryOutput
        ) | ConvertFrom-Json
        if (
            $marker.native_exit_code -notin @(0, 2) -or
            $marker.native_exit_code -ne $summary.return_code
        ) {
            throw "p4 QEP resume marker exit code is not bound to its summary."
        }
        return
    }
    Assert-FormalSourceStable -ExpectedSha $CommitSha
    if (Test-Path -LiteralPath $SummaryOutput -PathType Leaf) {
        Remove-Item -LiteralPath $SummaryOutput -Force
    }
    Write-Host "[run p4 pass-or-controlled-numerical-negative] $StepName"
    $dockerArguments = Get-DockerRunArguments -ContainerCommand $ContainerCommand
    $exitCode = Invoke-NativeStreaming `
        -FilePath $DockerExecutable `
        -ArgumentList $dockerArguments
    if ($exitCode -notin @(0, 2)) {
        throw "p4 QEP step $StepName failed with non-controlled exit $exitCode."
    }
    $summary = Assert-QepP4ControlledOutcome `
        -SummaryOutput $SummaryOutput `
        -MaterialKind $MaterialKind `
        -HNm $HNm `
        -AttemptRoot $AttemptRoot
    if ($summary.return_code -ne $exitCode) {
        throw "p4 QEP watchdog return code differs from Docker exit code."
    }
    Complete-Step -StepName $StepName -Outputs $outputs -ExitCode $exitCode
}

function Get-HybridFunnelSolverRecord {
    param(
        [Parameter(Mandatory = $true)][psobject]$Summary,
        [Parameter(Mandatory = $true)][string]$AttemptRoot
    )

    if (
        $null -eq $Summary.solver_record_ignored_path -or
        [string]::IsNullOrWhiteSpace(
            [string]$Summary.solver_record_ignored_path
        ) -or
        [string]$Summary.solver_record_sha256 -notmatch '^[0-9a-f]{64}$'
    ) {
        throw "Hybrid funnel watchdog has no complete solver-record descriptor."
    }
    $rawPath = [string]$Summary.solver_record_ignored_path
    $solverPath = if ([IO.Path]::IsPathRooted($rawPath)) {
        [IO.Path]::GetFullPath($rawPath)
    } else {
        [IO.Path]::GetFullPath((Join-Path $RepoRoot $rawPath))
    }
    $attemptPrefix = [IO.Path]::GetFullPath($AttemptRoot).TrimEnd(
        [char[]]@(47, 92)
    ) + [IO.Path]::DirectorySeparatorChar
    if (-not $solverPath.StartsWith(
        $attemptPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Hybrid funnel solver record is not bound to its attempt root."
    }
    if (-not (Test-Path -LiteralPath $solverPath -PathType Leaf)) {
        throw "Hybrid funnel solver record is missing: $solverPath"
    }
    $observedSha = Get-FileSha256 -Path $solverPath
    if ($observedSha -ne ([string]$Summary.solver_record_sha256).ToLowerInvariant()) {
        throw "Hybrid funnel solver-record SHA256 does not match its watchdog."
    }
    $record = Get-Content -Raw -LiteralPath $solverPath | ConvertFrom-Json
    $requiredProjectionKeys = @(
        "case",
        "solve",
        "gates",
        "qualification"
    )
    foreach ($key in $requiredProjectionKeys) {
        $embeddedProperty = $Summary.measurements.PSObject.Properties[$key]
        $recordProperty = $record.PSObject.Properties[$key]
        if ($null -eq $embeddedProperty -or $null -eq $recordProperty) {
            throw "Hybrid funnel projection lacks required solver field $key."
        }
        $embedded = $embeddedProperty.Value | ConvertTo-Json -Depth 100 -Compress
        $preserved = $recordProperty.Value | ConvertTo-Json -Depth 100 -Compress
        if ($embedded -ne $preserved) {
            throw "Hybrid funnel projection differs from solver field $key."
        }
    }
    foreach ($key in @("port_power", "external_diffraction_orders")) {
        $embeddedProperty = (
            $Summary.measurements.validation.PSObject.Properties[$key]
        )
        $recordProperty = $record.validation.PSObject.Properties[$key]
        if ($null -eq $embeddedProperty -or $null -eq $recordProperty) {
            throw "Hybrid funnel validation projection lacks required field $key."
        }
        $embedded = $embeddedProperty.Value | ConvertTo-Json -Depth 100 -Compress
        $preserved = $recordProperty.Value | ConvertTo-Json -Depth 100 -Compress
        if ($embedded -ne $preserved) {
            throw "Hybrid funnel validation projection differs for field $key."
        }
    }
    return $record
}

function Assert-HybridFunnelShardOutcome {
    param(
        [Parameter(Mandatory = $true)][string]$SummaryOutput,
        [Parameter(Mandatory = $true)][int]$Degree,
        [Parameter(Mandatory = $true)][string]$HNm,
        [Parameter(Mandatory = $true)][int]$RequestedModes,
        [Parameter(Mandatory = $true)][int]$CandidateModes,
        [Parameter(Mandatory = $true)][string]$AttemptRoot
    )

    if (-not (Test-Path -LiteralPath $SummaryOutput -PathType Leaf)) {
        throw "Hybrid funnel step produced no watchdog summary."
    }
    $summary = Get-Content -Raw -LiteralPath $SummaryOutput | ConvertFrom-Json
    $record = Get-HybridFunnelSolverRecord `
        -Summary $summary `
        -AttemptRoot $AttemptRoot
    $command = @($summary.command)
    $residual = [double]$record.solve.true_relative_residual
    $commonChecks = [ordered]@{
        schema_version = (
            $summary.schema_version -eq "task033.memory-watchdog.v2"
        )
        benchmark_id = (
            $summary.benchmark_id -eq "task033_external_memory_watchdog"
        )
        target = ($summary.target -eq "hybrid")
        requested_modes = ($summary.requested_modes -eq $RequestedModes)
        candidate_modes = ($summary.candidate_modes -eq $CandidateModes)
        command_requested_modes = (
            [int](Get-Task033CommandValue `
                -Command $command `
                -Option "--requested-modes") -eq $RequestedModes
        )
        command_candidate_modes = (
            (Get-Task033CommandValue `
                -Command $command `
                -Option "--candidate-modes") -eq "$CandidateModes"
        )
        command_degree = (
            [int](Get-Task033CommandValue `
                -Command $command `
                -Option "--degree") -eq $Degree
        )
        command_h_nm = (
            [double](Get-Task033CommandValue `
                -Command $command `
                -Option "--h-nm") -eq [double]$HNm
        )
        command_solver_path = (
            (Get-Task033CommandValue `
                -Command $command `
                -Option "--solver-path") -eq "modal-schur-memory-minimal"
        )
        memory_authority_pass = ($summary.memory_authority_pass -eq $true)
        no_swap = ($summary.no_swap -eq $true)
        not_terminated_for_memory = (
            $summary.terminated_for_memory -eq $false
        )
        not_terminated_for_timeout = (
            $summary.terminated_for_timeout -eq $false
        )
        authority_readable = (
            $summary.terminated_for_authority_unreadable -eq $false
        )
        resource_gate = ($summary.resource_authority.gate.pass -eq $true)
        source_gate = ($summary.source_gate.pass -eq $true)
        launch_gate = ($summary.launch_gate.pass -eq $true)
        degree = ($record.case.degree -eq $Degree)
        h_nm = ($record.case.h_nm -eq [double]$HNm)
        record_requested_modes = (
            $record.case.requested_modes_per_direction -eq $RequestedModes
        )
        record_candidate_modes = (
            $record.case.candidate_modes_per_target_branch -eq $CandidateModes
        )
        solver_path = (
            $record.hybrid_system.primary_solver_path -eq (
                "modal-schur-memory-minimal"
            )
        )
        embedded_solver_path = (
            $summary.measurements.hybrid_system.primary_solver_path -eq (
                "modal-schur-memory-minimal"
            )
        )
        finite_true_residual = (
            -not [double]::IsNaN($residual) -and
            -not [double]::IsInfinity($residual) -and
            $residual -ge 0.0 -and
            $residual -le 1.0e-9
        )
    }
    $failedCommonChecks = @(
        $commonChecks.GetEnumerator() |
            Where-Object { $_.Value -ne $true } |
            ForEach-Object { $_.Key }
    )
    if ($failedCommonChecks.Count -ne 0) {
        throw (
            "Hybrid funnel shard failed identity/resource/algebraic checks: " +
            ($failedCommonChecks -join ", ")
        )
    }

    if ($summary.status -eq "measured_shard_pass") {
        Assert-WatchdogPass -Outputs @($SummaryOutput)
        return $summary
    }

    $qualification = $record.qualification
    if (
        $summary.status -ne "formal_not_pass" -or
        $summary.formal_pass -ne $false -or
        $summary.numeric_pass -ne $false -or
        $summary.return_code -ne 2 -or
        $record.status -ne "physical_integration_failed" -or
        $qualification.integration_pass -ne $false -or
        $qualification.algebraic_chain_pass -ne $true -or
        $qualification.task033_physical_truncation_allowed -ne $true -or
        $qualification.mode_count_converged -ne $false -or
        $qualification.physical_field_gates_pass -ne $false -or
        $qualification.official_record -ne $false
    ) {
        throw "Hybrid funnel exit 2 is not a controlled physical truncation negative."
    }
    $allowedFalseGates = @(
        "sampled_interface_h_t_relative_l2_le_1e-2",
        "volume_absorption_full3d_abs_delta_le_1e-5",
        "middle_plane_e_relative_l2_le_5e-3",
        "middle_plane_h_relative_l2_le_5e-3"
    )
    $gateProperties = @($record.gates.PSObject.Properties)
    $invalidGateTypes = @(
        $gateProperties | Where-Object { $_.Value -isnot [bool] }
    )
    $falseGates = @(
        $gateProperties |
            Where-Object { $_.Value -eq $false } |
            ForEach-Object { $_.Name }
    )
    $unexpectedFalseGates = @(
        $falseGates | Where-Object { $_ -notin $allowedFalseGates }
    )
    if (
        $gateProperties.Count -eq 0 -or
        $invalidGateTypes.Count -ne 0 -or
        $falseGates.Count -eq 0 -or
        $unexpectedFalseGates.Count -ne 0
    ) {
        throw (
            "Hybrid intermediate negative has absent or non-whitelisted " +
            "physical Gate failures: " + ($unexpectedFalseGates -join ", ")
        )
    }
    return $summary
}

function Invoke-DockerHybridFunnelShardStep {
    param(
        [Parameter(Mandatory = $true)][string]$StepName,
        [Parameter(Mandatory = $true)][string[]]$ContainerCommand,
        [Parameter(Mandatory = $true)][string]$SummaryOutput,
        [Parameter(Mandatory = $true)][int]$Degree,
        [Parameter(Mandatory = $true)][string]$HNm,
        [Parameter(Mandatory = $true)][int]$RequestedModes,
        [Parameter(Mandatory = $true)][int]$CandidateModes,
        [Parameter(Mandatory = $true)][string]$AttemptRoot,
        [switch]$RequalificationRequired
    )

    $outputs = @($SummaryOutput)
    if (Test-StepComplete -StepName $StepName -Outputs $outputs) {
        $summary = Assert-HybridFunnelShardOutcome `
            -SummaryOutput $SummaryOutput `
            -Degree $Degree `
            -HNm $HNm `
            -RequestedModes $RequestedModes `
            -CandidateModes $CandidateModes `
            -AttemptRoot $AttemptRoot
        $marker = Get-Content -Raw -LiteralPath (
            Get-StepMarkerPath -PrimaryOutput $SummaryOutput
        ) | ConvertFrom-Json
        if (
            $marker.native_exit_code -notin @(0, 2) -or
            $marker.native_exit_code -ne $summary.return_code
        ) {
            throw "Hybrid funnel resume marker exit code differs from its summary."
        }
        if ($RequalificationRequired) {
            Assert-P2H3Requalification `
                -Outputs $outputs `
                -ExpectedRequestedModes $RequestedModes
        }
        return
    }
    Assert-FormalSourceStable -ExpectedSha $CommitSha
    if (Test-Path -LiteralPath $SummaryOutput -PathType Leaf) {
        Remove-Item -LiteralPath $SummaryOutput -Force
    }
    Write-Host "[run Hybrid funnel pass-or-controlled-physical-negative] $StepName"
    $dockerArguments = Get-DockerRunArguments -ContainerCommand $ContainerCommand
    $exitCode = Invoke-NativeStreaming `
        -FilePath $DockerExecutable `
        -ArgumentList $dockerArguments
    if ($exitCode -notin @(0, 2)) {
        throw "Hybrid funnel step $StepName failed with exit code $exitCode."
    }
    $summary = Assert-HybridFunnelShardOutcome `
        -SummaryOutput $SummaryOutput `
        -Degree $Degree `
        -HNm $HNm `
        -RequestedModes $RequestedModes `
        -CandidateModes $CandidateModes `
        -AttemptRoot $AttemptRoot
    if ($summary.return_code -ne $exitCode) {
        throw "Hybrid funnel watchdog return code differs from Docker exit code."
    }
    if ($RequalificationRequired) {
        Assert-P2H3Requalification `
            -Outputs $outputs `
            -ExpectedRequestedModes $RequestedModes
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
        $requalification.checks.candidate_pool_is_twice_requested_modes `
            -ne $true -or
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

function Assert-AdaptiveFormalPass {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][double]$ExpectedReferenceH
    )

    $record = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if (
        $record.status -ne "measured_same_accuracy_qualification_attached" -or
        $record.plan.reference_h_nm -ne $ExpectedReferenceH -or
        $record.same_accuracy_qualification.mandatory_gate_pass -ne $true
    ) {
        throw "Adaptive h=$ExpectedReferenceH formal same-accuracy gate did not pass."
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
        [switch]$ExpectedTimeoutNegative,
        [switch]$AllowP4ControlledNumericalNegative,
        [switch]$AllowHybridIntermediatePhysicalNegative
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
            "--high-order-core-evidence-sha256",
            $Case090AggregateEvidenceSha256
        )
    }

    [IO.Directory]::CreateDirectory((Split-Path -Parent $SummaryOutput)) | Out-Null
    [IO.Directory]::CreateDirectory($AttemptRoot) | Out-Null
    if (
        ($ExpectedTimeoutNegative -and $AllowP4ControlledNumericalNegative) -or
        (
            $ExpectedTimeoutNegative -and
            $AllowHybridIntermediatePhysicalNegative
        ) -or
        (
            $AllowP4ControlledNumericalNegative -and
            $AllowHybridIntermediatePhysicalNegative
        )
    ) {
        throw "A watchdog step cannot enable multiple controlled-negative modes."
    }
    if ($ExpectedTimeoutNegative) {
        Invoke-DockerTimeoutNegativeStep `
            -StepName $StepName `
            -ContainerCommand $command `
            -SummaryOutput $SummaryOutput
    } elseif ($AllowP4ControlledNumericalNegative) {
        if ($Target -ne "qep" -or $Degree -ne 4 -or $MpiSize -ne 1) {
            throw "Controlled numerical negatives are restricted to QEP p4 MPI1."
        }
        Invoke-DockerQepP4Step `
            -StepName $StepName `
            -ContainerCommand $command `
            -SummaryOutput $SummaryOutput `
            -MaterialKind $MaterialKind `
            -HNm $HNm `
            -AttemptRoot $AttemptRoot
    } elseif ($AllowHybridIntermediatePhysicalNegative) {
        if (
            $Target -ne "hybrid" -or
            $RequestedModes -notin @(80, 120) -or
            $CandidateModes -ne (2 * $RequestedModes) -or
            $SolverPath -ne "modal-schur-memory-minimal" -or
            $CompareModalSchur
        ) {
            throw (
                "Controlled Hybrid physical negatives are restricted to " +
                "memory-minimal M80/M120 funnel shards."
            )
        }
        Invoke-DockerHybridFunnelShardStep `
            -StepName $StepName `
            -ContainerCommand $command `
            -SummaryOutput $SummaryOutput `
            -Degree $Degree `
            -HNm $HNm `
            -RequestedModes $RequestedModes `
            -CandidateModes $CandidateModes `
            -AttemptRoot $AttemptRoot `
            -RequalificationRequired:$AnchorRequalification
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
        [switch]$AnchorRequalification,
        [switch]$AllowConditionalM240
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
            -CandidateModes (2 * $modeCount) `
            -SummaryOutput $summary `
            -AttemptRoot (Join-Path $modeRoot "attempts") `
            -SolverPath "modal-schur-memory-minimal" `
            -BottomInterfaceNm $BottomInterfaceNm `
            -TopInterfaceNm $TopInterfaceNm `
            -GradedReferenceH $GradedReferenceH `
            -AnchorRequalification:$AnchorRequalification `
            -AllowHybridIntermediatePhysicalNegative:(
                $modeCount -in @(80, 120)
            ) `
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
    $conditionalM240InScope = (
        [bool]$AllowConditionalM240 -and
        $Category -eq "uniform" -and
        $Degree -in @(3, 4) -and
        -not $GradedReferenceH -and
        $BottomInterfaceNm -eq "10.0" -and
        $TopInterfaceNm -eq "110.0"
    )
    if (-not $conditionalM240InScope) {
        throw (
            "Funnel $Name has measured M120->M160 nonconvergence, but " +
            "conditional M240 is restricted to explicitly authorized " +
            "uniform p3/p4 cases."
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
        -CandidateModes 480 `
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
        -CandidateModes 320 `
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
mem_available_kib = next(
    int(line.split()[1])
    for line in Path('/proc/meminfo').read_text().splitlines()
    if line.startswith('MemAvailable:')
)
host_available = mem_available_kib * 1024
payload = {
    'memory_max_bytes': memory_max,
    'memory_swap_max_bytes': swap_max,
    'memory_swap_current_bytes': swap_current,
    'host_available_memory_bytes': host_available,
}
print(json.dumps(payload, sort_keys=True))
raise SystemExit(
    0
    if (
        memory_max == 13958643712
        and swap_max == 0
        and swap_current == 0
        and host_available >= 12884901888
    )
    else 2
)
'@
    $preflightArgs = Get-DockerRunArguments -ContainerCommand @(
        "python", "-c", $preflightCode
    )
    $preflightResult = Invoke-NativeCapture `
        -FilePath $DockerExecutable `
        -ArgumentList $preflightArgs
    if ($preflightResult.ExitCode -ne 0) {
        throw (
            "13g/no-swap Docker cgroup and 12 GiB host-available " +
            "runtime-guard preflight failed."
        )
    }
    $cgroup = $preflightResult.Text | ConvertFrom-Json
    if (
        $cgroup.memory_max_bytes -ne $ExpectedMemoryMaxBytes -or
        $cgroup.memory_swap_max_bytes -ne 0 -or
        $cgroup.memory_swap_current_bytes -ne 0 -or
        $cgroup.host_available_memory_bytes -lt $ExpectedRuntimeGuardBytes
    ) {
        throw (
            "Docker authority is not 13g/no-swap with at least the 12 GiB " +
            "Task033 runtime guard available."
        )
    }
    $preflightRecord = [ordered]@{
        schema_version = "task033.formal-campaign-preflight.v1"
        source_commit_full_sha = $CommitSha
        complete_nonignored_worktree_clean = $true
        docker_image = $DockerImage
        docker_image_digest = $ImageDigest
        docker_repo_digests = $DockerRepoDigests
        host_aggregation_runtime = $HostAggregationRuntime
        container_git_checkout_normalization = "core.autocrlf=true"
        cgroup = $cgroup
        runtime_guard_budget_gib = $RuntimeGuardBudgetGiB
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
    $case090AggregatePayload = Get-Content `
        -Raw `
        -LiteralPath $Case090Aggregate | ConvertFrom-Json
    $Case090AggregateEvidenceSha256 = "$($case090AggregatePayload.evidence_sha256)".ToLowerInvariant()
    if ($Case090AggregateEvidenceSha256 -notmatch '^[0-9a-f]{64}$') {
        throw "Case090 aggregate lacks one canonical evidence_sha256."
    }

    # Phase 2: the formal 36-shard MPI1 QEP matrix plus explicit MPI2/MPI4
    # timeout-only negatives.  All 27 p1-p3 shards are strict passes.  Every
    # p4 shard must finish and may continue only as a pass or an exit-2,
    # record-backed, controlled numerical negative.
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
                    -CandidateModes 16 `
                    -SummaryOutput $passSummary `
                    -AttemptRoot (Join-Path $passRoot "attempts") `
                    -MaterialKind $material `
                    -TimeoutSeconds $QepTimeoutSeconds `
                    -AllowP4ControlledNumericalNegative:($degree -eq 4)

            }
        }
    }
    # MPI2/MPI4 are bounded clean wall-timeout diagnostics, not another
    # 72-member physical matrix.  They prove only the watchdog/source/resource
    # timeout contract; they do not attribute the timeout to a PEP/MUMPS
    # boundary.  One fixed patterned p2/h3 case per communicator is sufficient
    # and keeps the diagnostic evidence distinct from the qualified MPI1 aggregate.
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
            -CandidateModes 16 `
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
        $allowConditionalM240 = $entry.Degree -in @(3, 4)
        $uniformFunnels[$entry.Key] = Invoke-HybridFunnel `
            -Name $entry.Key `
            -Category "uniform" `
            -Degree $entry.Degree `
            -HNm $entry.H `
            -AnchorRequalification:$requalify `
            -AllowConditionalM240:$allowConditionalM240
    }

    # Task033 8.3 anchors: augmented primary versus the memory-minimal Schur
    # comparison.  Never rely on the inherited fast comparison default.
    $p1Anchor = Invoke-HybridComparisonAnchor -Name "p1_h5" -Degree 1
    $p3Anchor = Invoke-HybridComparisonAnchor -Name "p3_h5" -Degree 3
    Write-Host "comparison anchors: $p1Anchor ; $p3Anchor"

    # Phase 4: adaptive evidence is strictly gated.  The h5 funnel and formal
    # same-accuracy aggregate must pass before the h3 funnel is launched.
    $aggregateRoot = Join-Path $ArtifactRootHost "aggregates"
    [IO.Directory]::CreateDirectory($aggregateRoot) | Out-Null
    $gradedFunnels = @{}
    $gradedFunnels["p2_h5_graded"] = Invoke-HybridFunnel `
        -Name "p2_h5_graded" `
        -Category "graded" `
        -Degree 2 `
        -HNm "5.0" `
        -GradedReferenceH "5.0"

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
            $gradedFunnels["p2_h5_graded"],
            "--repo-root", $RepoRoot
        ) `
        -Output $adaptiveH5
    Assert-AdaptiveFormalPass -Path $adaptiveH5 -ExpectedReferenceH 5.0

    $gradedFunnels["p2_h3_graded"] = Invoke-HybridFunnel `
        -Name "p2_h3_graded" `
        -Category "graded" `
        -Degree 2 `
        -HNm "3.0" `
        -GradedReferenceH "3.0"

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
            $gradedFunnels["p2_h3_graded"],
            "--repo-root", $RepoRoot
        ) `
        -Output $adaptiveH3
    Assert-AdaptiveFormalPass -Path $adaptiveH3 -ExpectedReferenceH 3.0

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
    $qepAggregate = Join-Path $aggregateRoot "qep_order_study.json"
    $qepAggregateCommand = @(
        "-m", "benchmarks.run_task033_formal_records",
        "qep-order-study", "--mpi-size", "1",
        "--repo-root", $RepoRoot
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
        "--repo-root", $RepoRoot,
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

    $bufferAggregate = Join-Path $aggregateRoot "buffer_tradeoff.json"
    Invoke-HostJsonCaptureStep `
        -StepName "aggregate_buffer_tradeoff" `
        -PythonArguments @(
            "-m", "benchmarks.run_task033_formal_records",
            "buffer-tradeoff",
            $bufferFunnels["buffer_10"],
            $bufferFunnels["buffer_7p5"],
            $bufferFunnels["buffer_5"],
            $bufferFunnels["buffer_2p5"],
            "--repo-root", $RepoRoot
        ) `
        -Output $bufferAggregate

    $equalAccuracy = Join-Path $aggregateRoot "equal_accuracy.json"
    $equalAccuracyCommand = @(
        "-m", "benchmarks.run_task033_equal_accuracy",
        "--reference",
        $uniformFunnels["p2_h3"],
        "--repo-root", $RepoRoot,
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
    foreach ($gradedKey in @("p2_h5_graded", "p2_h3_graded")) {
        $equalAccuracyCommand += @(
            "--candidate",
            $gradedFunnels[$gradedKey]
        )
    }
    $equalAccuracyCommand += "--require-qualified"
    Invoke-HostFileStep `
        -StepName "aggregate_equal_accuracy" `
        -PythonArguments $equalAccuracyCommand `
        -Outputs @($equalAccuracy)

    # Variable-p has no evidence-selection ambiguity, so produce its formal
    # fail-closed capability audit on the same clean SHA now.
    $variableP = Join-Path $aggregateRoot "variable_p_capability_audit.json"
    Invoke-DockerFileStep `
        -StepName "aggregate_variable_p_capability_audit" `
        -ContainerCommand @(
            "python", "-m", "benchmarks.run_task033_variable_p_audit",
            "--formal", "--repo-root", "/work",
            "--output", (Convert-ToContainerPath -HostPath $variableP)
        ) `
        -Outputs @($variableP)

    # Phase 7: the equal-accuracy record has already re-opened and checked every
    # candidate watchdog.  The projection builder independently revalidates its
    # schema, payload hash, best-candidate selection, local-DoF ratio, and clean
    # source SHA before classifying the conservative 0.7 nm row scenario.
    $oneTib = Join-Path $aggregateRoot "one_tib_projection.json"
    Invoke-HostFileStep `
        -StepName "aggregate_one_tib_projection" `
        -PythonArguments @(
            "-m", "benchmarks.run_task033_one_tib_projection",
            "--compression-evidence", $equalAccuracy,
            "--formal", "--repo-root", $RepoRoot,
            "--output", $oneTib
        ) `
        -Outputs @($oneTib)

    # The supplemental task-level classifier consumes both distributed-QEP
    # timeout negatives and all primary aggregates.  A clean timeout remains a
    # legitimate negative diagnostic, so --require-nonfailed accepts the
    # expected partial result but rejects any mandatory evidence failure.
    $finalOutcome = Join-Path $aggregateRoot "final_outcome_classification.json"
    Invoke-HostFileStep `
        -StepName "aggregate_final_outcome" `
        -PythonArguments @(
            "-m", "benchmarks.run_task033_final_outcome",
            "--case090-core", $Case090Aggregate,
            "--qep-mpi1-aggregate", $qepAggregate,
            "--qep-mpi2-timeout-negative", (Join-Path $ArtifactRootHost "qep/timeout_negatives/mpi2/stage4_xy_p2_h3/watchdog_summary.json"),
            "--qep-mpi4-timeout-negative", (Join-Path $ArtifactRootHost "qep/timeout_negatives/mpi4/stage4_xy_p2_h3/watchdog_summary.json"),
            "--augmented-vs-minimal-p1", $p1Anchor,
            "--augmented-vs-minimal-p3", $p3Anchor,
            "--uniform-p-h-matrix", $uniformAggregate,
            "--equal-accuracy", $equalAccuracy,
            "--adaptive-p2-h5", $adaptiveH5,
            "--adaptive-p2-h3", $adaptiveH3,
            "--interface-buffer-tradeoff", $bufferAggregate,
            "--variable-p-capability-audit", $variableP,
            "--one-tib-projection", $oneTib,
            "--expected-source-sha", $CommitSha,
            "--repo-root", $RepoRoot,
            "--output", $finalOutcome,
            "--require-nonfailed"
        ) `
        -Outputs @($finalOutcome)

    # Build the frozen evidence-integrity manifest and immediately run the
    # independent checker.  This manifest deliberately does not claim that a
    # clean timeout diagnostic is a positive MPI QEP/interface qualification.
    $formalManifest = Join-Path $aggregateRoot "formal_evidence_manifest.json"
    $formalManifestCommand = @(
        "-m", "benchmarks.run_task033_formal_records",
        "formal-manifest", "--repo-root", $RepoRoot
    )
    $formalRolePaths = [ordered]@{
        "case090_clean_core" = $Case090Aggregate
        "case090_mpi_memory" = $Case090Aggregate
        "qep_order_study" = $qepAggregate
        "qep_mpi2_timeout_negative" = (Join-Path $ArtifactRootHost "qep/timeout_negatives/mpi2/stage4_xy_p2_h3/watchdog_summary.json")
        "qep_mpi4_timeout_negative" = (Join-Path $ArtifactRootHost "qep/timeout_negatives/mpi4/stage4_xy_p2_h3/watchdog_summary.json")
        "hybrid_funnel_p1" = $uniformFunnels["p1_h5"]
        "hybrid_funnel_p3" = $uniformFunnels["p3_h5"]
        "augmented_vs_minimal_p1" = $p1Anchor
        "augmented_vs_minimal_p3" = $p3Anchor
        "uniform_p_h_matrix" = $uniformAggregate
        "adaptive_p2_h5" = $adaptiveH5
        "adaptive_p2_h3" = $adaptiveH3
        "interface_buffer_10" = $bufferFunnels["buffer_10"]
        "interface_buffer_7p5" = $bufferFunnels["buffer_7p5"]
        "interface_buffer_5" = $bufferFunnels["buffer_5"]
        "interface_buffer_2p5" = $bufferFunnels["buffer_2p5"]
        "interface_buffer_tradeoff" = $bufferAggregate
        "equal_accuracy" = $equalAccuracy
        "variable_p_capability_audit" = $variableP
        "one_tib_projection" = $oneTib
        "final_outcome" = $finalOutcome
    }
    foreach ($role in $formalRolePaths.Keys) {
        $formalManifestCommand += @(
            "--role",
            "$role=$(Convert-ToRepoRelativePath -HostPath $formalRolePaths[$role])"
        )
    }
    Invoke-HostJsonCaptureStep `
        -StepName "aggregate_formal_evidence_manifest" `
        -PythonArguments $formalManifestCommand `
        -Output $formalManifest

    $formalVerification = Join-Path $aggregateRoot "formal_verification.json"
    Invoke-HostJsonCaptureStep `
        -StepName "verify_formal_evidence_manifest" `
        -PythonArguments @(
            "-m", "benchmarks.check_task033",
            "--repo-root", $RepoRoot,
            "--formal-manifest", $formalManifest,
            "--require-formal"
        ) `
        -Output $formalVerification

    # The checker report cannot be a manifest role because it is produced from
    # that manifest.  Bind the manifest, verification, and final outcome only
    # after verification, in a separate self-hashed publication descriptor.
    $publicationDescriptor = Join-Path $aggregateRoot (
        "formal_publication_descriptor.json"
    )
    Invoke-HostJsonCaptureStep `
        -StepName "aggregate_formal_publication_descriptor" `
        -PythonArguments @(
            "-m", "benchmarks.run_task033_formal_records",
            "publication-descriptor",
            "--repo-root", $RepoRoot,
            "--formal-manifest", $formalManifest,
            "--formal-verification", $formalVerification,
            "--final-outcome", $finalOutcome
        ) `
        -Output $publicationDescriptor

    Assert-FormalSourceStable -ExpectedSha $CommitSha
    Write-Host "Task033 formal measurements, manifest, checker, and publication descriptor completed."
    Write-Host "Task-level pass/partial/negative classification remains evidence-derived."
} finally {
    if ($null -ne $campaignLock) {
        $campaignLock.Dispose()
    }
}
