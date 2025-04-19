# Install winget if not already installed
$wingetInstalled = Get-Command winget -ErrorAction SilentlyContinue
if (-not $wingetInstalled) {
    Invoke-WebRequest -Uri https://aka.ms/getwinget -OutFile winget.msixbundle
    Add-AppxPackage winget.msixbundle
    Remove-Item winget.msixbundle
}
# Install ffmpeg
winget install ffmpeg -e --accept-package-agreements --accept-source-agreements
