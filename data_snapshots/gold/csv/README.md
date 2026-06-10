# Static CSV snapshots for Gold

This folder stores static CSV snapshots used to recreate the Gold lakehouse in another workspace.

Expected folders:
- 01_dim_loan
- 02_dim_prev_application
- 03_dim_relative_month
- 04_dim_dpd_bucket_v2
- 05_fact_pos_cash_monthly_balance_v2

How to populate:
1. Export snapshots from Fabric package output path (Files/github_portable/gold/csv).
2. Copy each table CSV into its matching folder.
3. Commit and push.
