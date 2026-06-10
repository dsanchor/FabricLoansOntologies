# Runbook: GitHub + Fabric workspace bootstrap desde cero

## 1) Objetivo
Este documento define como:
- Conectar un workspace de Fabric a un repositorio GitHub.
- Respaldar los objetos necesarios para reproducir el entorno.
- Ejecutar el notebook de despliegue para crear/hidratar el Lakehouse Gold destino.
- Replicar el contenido en otros workspaces de forma controlada.

Este runbook esta alineado al entorno LoanDemoEnv y a la ontologia solicitada como AnalyceLoanV3 (resuelta en Fabric como AnalyzeLoanOnV3).

## 2) Alcance funcional del despliegue
El notebook de despliegue principal es:
- src/notebooks/fabric_gold_package_and_deploy.ipynb

Ese notebook permite:
- Exportar paquete portable CSV de tablas Gold.
- Crear (si falta) un Lakehouse de destino especifico.
- Hidratar tablas Delta en el Lakehouse destino.
- Validar tablas minimas requeridas para bootstrap de ontologia.
- Restaurar automaticamente la ontologia (entidades/nodos/relaciones) en el workspace destino.
- Reescribir y aplicar DataBindings de la ontologia hacia el Gold destino.
- Generar manifiestos de evidencia de despliegue.

## 3) Objetos que SI deben quedar versionados en GitHub
Versionar de forma obligatoria:
- src/notebooks/fabric_gold_package_and_deploy.ipynb
- docs/fabric_gold_package/package_context.csv
- docs/fabric_gold_package/ontology_scope.csv
- docs/fabric_gold_package/gold_objects.csv
- docs/fabric_gold_package/gold_notebooks.csv
- docs/github_fabric_workspace_bootstrap_runbook.md

Versionar recomendado (si aplica a tu proceso):
- scripts de validacion y auditoria en la raiz del repo.
- cualquier archivo de configuracion adicional de despliegue.

No versionar:
- secretos, tokens, credenciales.
- datos sensibles no anonimizados.
- salidas temporales de ejecucion o logs locales con datos confidenciales.

## 4) Estructura minima recomendada del repo
Mantener esta estructura minima:
- src/notebooks/
- docs/fabric_gold_package/
- docs/

Con esto, el repositorio queda portable para:
- backup
- DR (disaster recovery)
- replicacion entre workspaces

## 5) Como crear el repositorio en GitHub
Opcion web (recomendada):
1. Entrar a GitHub y crear un repositorio nuevo, preferentemente privado.
2. Nombre sugerido: fabric-gold-ontology-bootstrap.
3. Crear rama principal main.
4. Activar protecciones basicas de rama en main:
   - requerir pull request
   - bloquear force push

Opcional pero recomendado:
- Crear rama dev para cambios de trabajo.
- Usar releases o tags para versiones de despliegue (por ejemplo v1.0.0).

## 6) Como subir el contenido a GitHub
Desde VS Code o cliente Git:
1. Inicializar repositorio local si aun no existe.
2. Agregar remote origin apuntando al repositorio GitHub.
3. Agregar archivos versionables indicados en la seccion 3.
4. Commit inicial con mensaje claro, por ejemplo:
   - bootstrap: notebook gold deploy + manifests + runbook
5. Push a rama main (o a dev y luego PR a main).

Checklist previo al push:
- Validar que el notebook es JSON valido.
- Confirmar que no hay secretos en texto plano.
- Confirmar que el runbook y manifiestos estan actualizados.

## 7) Conectar un workspace de Fabric al repositorio GitHub
Pasos generales en Fabric (UI):
1. Abrir el workspace destino en Fabric.
2. Ir a configuracion de Git (Git integration / Source control).
3. Seleccionar proveedor GitHub.
4. Autorizar acceso si es la primera vez.
5. Seleccionar:
   - organizacion/usuario
   - repositorio
   - rama (main o la rama de despliegue)
   - carpeta raiz del proyecto
6. Completar la vinculacion.
7. Ejecutar Sync para traer el contenido del repo al workspace.

Buenas practicas:
- No conectar workspaces productivos directamente a ramas inestables.
- Usar una rama controlada para cada entorno (dev, qa, prod).

## 8) Despliegue desde cero en un workspace nuevo
### 8.1 Pre-requisitos
- Workspace con capacidad Fabric activa.
- Permisos para crear items (Lakehouse, Notebook) y ejecutar notebooks.
- Acceso al repositorio GitHub ya conectado al workspace.

### 8.2 Traer artefactos
1. Hacer Sync del workspace conectado al repo.
2. Confirmar que exista el notebook:
   - src/notebooks/fabric_gold_package_and_deploy.ipynb

### 8.3 Configurar parametros del notebook
En la celda de configuracion del notebook (celda 2), revisar:
- deploy_to_target = True
- target_workspace_id = workspace destino
- target_gold_lakehouse = nombre de Lakehouse objetivo
- target_gold_lakehouse_id = opcional (si ya existe)
- create_target_lakehouse_if_missing = True

Si el notebook no puede obtener token por runtime:
- asignar fabric_token_override temporalmente.
- nunca commitear ese token al repo.

### 8.4 Ejecutar notebook completo
Ejecutar de la celda 1 a la ultima.
Resultado esperado:
- Se crea o resuelve Lakehouse destino.
- Se hidratan tablas Delta Gold en el destino.
- Se valida presencia de tablas minimas para ontologia.
- Se crea o actualiza la ontologia en destino con relaciones y bindings listos para consulta.
- Se generan manifiestos de evidencia en Files/github_portable/gold/manifests.

### 8.5 Verificaciones post despliegue
Verificar en el Lakehouse destino las tablas clave:
- dbo.dim_loan
- dbo.dim_prev_application
- dbo.dim_relative_month
- dbo.dim_dpd_bucket_v2
- dbo.fact_pos_cash_monthly_balance_v2

Revisar manifiestos:
- gold_deployment_target
- gold_deployment_results
- ontology_target_binding_hint
- ontology_restore_results

## 9) Validar restauracion de ontologia en destino
El notebook ya realiza la restauracion de ontologia al final (si `restore_ontology_to_target = True`).
Validar:
1. Existe la ontologia destino con el nombre configurado.
2. Las entidades y relaciones se visualizan en la ontologia restaurada.
3. Los DataBindings apuntan al Lakehouse Gold destino (workspace/item objetivo).
4. El manifiesto `ontology_restore_results` reporta estado `ready`.

## 10) Estrategia de respaldo para replicar en otros workspaces
Para que el contenido quede bien respaldado y portable:
1. Mantener notebook y manifiestos siempre versionados.
2. Hacer release/tag por cada version estable de despliegue.
3. Guardar evidencias de cada ejecucion en una carpeta de auditoria (opcional).
4. Replicar con este flujo:
   - conectar nuevo workspace al repo
   - sync
   - ejecutar notebook
   - validar manifiestos, tablas y ontology_restore_results

## 11) Matriz de respaldo recomendada
- Notebook de despliegue: respaldo en GitHub (obligatorio)
- Lista de objetos Gold: respaldo en CSV (obligatorio)
- Scope de ontologia: respaldo en CSV (obligatorio)
- Evidencia de despliegue: respaldo en manifiestos de salida (recomendado)
- Definiciones de items adicionales (si aplica): respaldo en JSON exportado (recomendado)

## 12) Operacion continua
En cada cambio relevante:
1. Ajustar notebook y/o manifiestos.
2. Probar despliegue en entorno dev.
3. Commit + PR.
4. Merge a rama objetivo.
5. Sync en workspace objetivo.
6. Ejecutar notebook y validar.

Con este runbook, el repositorio queda como fuente unica de verdad para restaurar o replicar el entorno en cualquier workspace compatible de Fabric.
