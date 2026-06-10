param(
  [Parameter(Mandatory=$true)]
  [string]$SourceRoot,

  [string]$RepoRoot = "C:\Users\pahumada\OneDrive - Microsoft\Developer\Repos\dbxprojects\fabric-gold-package-repo"
)

$ErrorActionPreference = "Stop"

$mapping = @(
  @{Name="01_dim_loan"; Src="01_dim_loan"},
  @{Name="02_dim_prev_application"; Src="02_dim_prev_application"},
  @{Name="03_dim_relative_month"; Src="03_dim_relative_month"},
  @{Name="04_dim_dpd_bucket_v2"; Src="04_dim_dpd_bucket_v2"},
  @{Name="05_fact_pos_cash_monthly_balance_v2"; Src="05_fact_pos_cash_monthly_balance_v2"}
)

$targetBase = Join-Path $RepoRoot "data_snapshots\gold\csv"

foreach ($m in $mapping) {
  $srcDir = Join-Path $SourceRoot $m.Src
  $dstDir = Join-Path $targetBase $m.Name

  if (!(Test-Path $srcDir)) {
    Write-Warning "Source not found: $srcDir"
    continue
  }

  if (!(Test-Path $dstDir)) {
    New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
  }

  Get-ChildItem -Path $dstDir -File -Filter *.csv | Remove-Item -Force -ErrorAction SilentlyContinue
  Copy-Item -Path (Join-Path $srcDir "*.csv") -Destination $dstDir -Force

  $count = (Get-ChildItem -Path $dstDir -File -Filter *.csv | Measure-Object).Count
  Write-Host "$($m.Name): $count csv files"
}

Write-Host "Snapshot import complete."
