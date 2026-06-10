# Fabric Gold Workspace Rebuild Package

Este repositorio contiene solo lo necesario para recrear en otro workspace:
- Lakehouse Gold destino
- Tablas Delta Gold
- Ontologia restaurada automaticamente con sus bindings y relaciones

## Contenido
- src/notebooks/fabric_gold_package_and_deploy.ipynb
- docs/fabric_gold_package/package_context.csv
- docs/fabric_gold_package/ontology_scope.csv
- docs/fabric_gold_package/gold_objects.csv
- docs/fabric_gold_package/gold_notebooks.csv
- docs/fabric_gold_package/ontology_bootstrap_targets.csv
- docs/github_fabric_workspace_bootstrap_runbook.md

## Uso rapido
1. Conectar el workspace destino a este repo GitHub.
2. Sincronizar contenido del repo en Fabric.
3. Abrir y ejecutar el notebook src/notebooks/fabric_gold_package_and_deploy.ipynb.
4. Validar manifiestos de salida en Files/github_portable/gold/manifests.
5. Confirmar restauracion de ontologia en el manifiesto ontology_restore_results generado por el notebook.

## Restauracion automatica de ontologia
El notebook `src/notebooks/fabric_gold_package_and_deploy.ipynb` restaura automaticamente la ontologia en destino cuando `restore_ontology_to_target = True`:
- crea la ontologia si no existe
- actualiza la definicion completa (nodos/entidades/relaciones)
- reescribe los DataBindings para apuntar al Lakehouse Gold destino

## Alcance de tablas para AnalyzeLoanOnV3
El paquete actual incluye las tablas Gold que la ontologia referencia en sus DataBindings:
- dbo.dim_loan
- dbo.dim_prev_application
- dbo.dim_relative_month
- dbo.dim_dpd_bucket_v2
- dbo.fact_pos_cash_monthly_balance_v2
