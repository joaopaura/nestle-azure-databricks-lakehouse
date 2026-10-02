# Upload the raw files to the ADLS Gen2 landing zone (container "landing").
# Needs Azure CLI (az) and the role "Storage Blob Data Contributor" on the storage account.
#   cd C:\Portfolio\Nestle\nestle-azure-databricks-lakehouse
#   .\infra\upload_landing.ps1                 # public data, sell-out files, POS August
#   .\infra\upload_landing.ps1 -PosSeptember   # later (Phase 7): second POS batch for the streaming demo
param([string]$Account = "stnestlejp01", [switch]$PosSeptember)
$ErrorActionPreference = "Stop"
$raw = Join-Path $PSScriptRoot "..\data\raw"

function Upload($src, $dest, $pattern = "*") {
    Write-Host "Uploading $src -> landing/$dest ($pattern)" -ForegroundColor Cyan
    az storage blob upload-batch --account-name $Account --auth-mode login --destination landing `
        --destination-path $dest --source (Join-Path $raw $src) --pattern $pattern --overwrite --max-connections 8 --only-show-errors | Out-Null
}

if ($PosSeptember) {
    Upload "pos_stream" "pos_stream" "date=2026-09-*"
} else {
    Upload "public" "public"
    Upload "sellout" "sellout"
    Upload "pos_stream" "pos_stream" "date=2026-08-*"
}
Write-Host "Files in landing:" -ForegroundColor Green
foreach ($p in @("public", "sellout", "pos_stream")) {
    $names = az storage blob list --account-name $Account --auth-mode login -c landing --prefix "$p/" --num-results 100000 --query "[].name" -o tsv --only-show-errors
    $n = @($names).Count
    Write-Host ("  {0,-12} {1,6} files" -f $p, $n)
}
