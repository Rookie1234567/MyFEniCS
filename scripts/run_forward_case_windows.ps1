param(
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$Distribution = "Ubuntu-24.04",
    [string]$RepositoryWslPath = "/home/shenjh/Projects/MyFEniCS-Surrogate",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$distributions = & wsl.exe --list --quiet
if ($LASTEXITCODE -ne 0 -or $distributions -notcontains $Distribution) {
    throw "Required WSL distribution '$Distribution' is unavailable."
}

$configWsl = (& wsl.exe -d $Distribution -- wslpath -a $ConfigPath).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to convert config path to WSL." }
$outputWsl = (& wsl.exe -d $Distribution -- wslpath -a $OutputPath).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to convert output path to WSL." }
$stagingWsl = "$RepositoryWslPath/benchmarks/artifacts/task000/windows-launcher"

$dryToken = if ($DryRun) { "--dry-run" } else { "" }
$command = 'cd "$1" && scripts/run_forward_case.sh --config "$2" --output "$3" $5 && mkdir -p "$4" && cp -a "$3"/. "$4"/'
& wsl.exe -d $Distribution -- bash -lc $command task000-launcher `
    $RepositoryWslPath $configWsl $stagingWsl $outputWsl $dryToken
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Error "WSL forward case failed with exit code $exitCode."
}
exit $exitCode
