param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet('test','regression','mutate','build')][string]$Command,
    [Parameter(Mandatory=$true, Position=1)][string]$Core,
    [string]$Suite = 'smoke',
    [string]$Check,
    [string]$RomDir,
    [string]$Output,
    [int]$Seed = 1,
    [Alias('Profile')][string]$BuildProfile = 'candidate',
    [string]$Distribution = 'Ubuntu-24.04'
)
$ErrorActionPreference = 'Stop'
function Convert-WslPath([string]$Value) {
    $absolute = [System.IO.Path]::GetFullPath($Value)
    $converted = & wsl.exe -d $Distribution -- wslpath -a -u $absolute
    if ($LASTEXITCODE -ne 0) { throw "Could not convert path for WSL: $absolute" }
    return $converted.Trim()
}
$frameworkScript = Convert-WslPath (Join-Path $PSScriptRoot 'mister-bdsm')
$corePath = Convert-WslPath $Core
$arguments = @('-d', $Distribution, '--', 'python3', $frameworkScript, $Command, $corePath, '--suite', $Suite, '--seed', $Seed, '--profile', $BuildProfile)
if ($Check) { $arguments += @('--check', $Check) }
if ($RomDir) { $arguments += @('--rom-dir', (Convert-WslPath $RomDir)) }
if ($Output) { $arguments += @('--output', (Convert-WslPath $Output)) }
& wsl.exe @arguments
exit $LASTEXITCODE
