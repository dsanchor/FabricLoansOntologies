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

## Fabric for newbies

Esta seccion despliega **solo las tablas Gold** (sin ontologia) usando el script
`scripts/deploy_to_fabric.py`. Es la via mas sencilla si eres nuevo en Fabric: no
necesitas el notebook ni el workspace de origen, solo una capacidad Fabric y un
workspace destino en tu propia suscripcion.

> Conceptos rapidos:
> - **Capacidad** = el recurso de Azure que paga el computo (SKU tipo F2). En Fabric tambien existe una **prueba gratuita** que sirve para esto.
> - **Workspace** = la carpeta logica en Fabric donde viven tus items; se asigna a una capacidad.
> - **Lakehouse** = el almacen donde quedaran las 5 tablas Delta.

### 1. Crear la capacidad (o activar la prueba gratuita)
Opcion A — Prueba gratuita (recomendada para empezar):
1. Entra a https://app.fabric.microsoft.com
2. Activa el **Trial** de Fabric desde el menu de tu cuenta. Cero coste.

Opcion B — Capacidad de pago en Azure:
1. Entra a https://portal.azure.com y busca **Microsoft Fabric** -> **Create**.
2. Elige suscripcion, resource group, nombre y region.
3. Tamano **F2** (el mas pequeno) basta para probar.
4. **Review + Create**. (Pausa la capacidad cuando no la uses: factura por hora.)

### 2. Crear el workspace destino
1. En https://app.fabric.microsoft.com ve a **Workspaces** -> **+ New workspace**.
2. Ponle nombre (p.ej. `LoanDemo-MiEntorno`).
3. En **Advanced > License mode** selecciona tu **Trial** o tu **Capacity**.
4. **Apply**. Asegurate de tener rol **Admin** (lo tienes si lo creaste tu).
5. Copia el **GUID del workspace** desde la URL: `.../groups/<ESTE-GUID>/...`.

### 3. Preparar el entorno local y la configuracion
```bash
# 1. Instalar dependencias del script
pip install -r scripts/requirements.txt

# 2. Materializar los datos reales (los .zip del repo son punteros Git LFS)
git lfs install
git lfs pull

# 3. Crear tu .env a partir de la plantilla y rellenarlo
cp .env.example .env
#    Edita .env: como minimo FABRIC_TENANT_ID y FABRIC_TARGET_WORKSPACE_ID
```
Variables minimas en `.env`:
- `FABRIC_TENANT_ID`: GUID de tu tenant (Azure > Microsoft Entra ID > Overview).
- `FABRIC_TARGET_WORKSPACE_ID`: GUID del workspace del paso 2.

> Si tu repo esta en una ruta sincronizada por OneDrive o montada (`/mnt/c/...`),
> deja `FABRIC_WORKDIR=` vacio: el script usa el directorio temporal del sistema
> para evitar errores `Upload aborted` al escribir Parquet.

### 4. Subir las tablas
```bash
# Validacion previa sin tocar Fabric (recomendado la primera vez)
python scripts/deploy_to_fabric.py --dry-run

# Despliegue real: crea el lakehouse y sube las 5 tablas Delta
python scripts/deploy_to_fabric.py
```
El script:
1. Valida que los ZIPs tienen datos reales (no punteros LFS).
2. Se autentica contra Azure AD (interactive / device / cli segun `FABRIC_AUTH_METHOD`).
3. Crea (o reutiliza) el Lakehouse `Gold_AnalyzeLoanV3_Target` via Fabric REST.
4. Convierte cada CSV a Delta localmente y lo sube a `Tables/dbo/<tabla>` en OneLake.

### 5. Ver las tablas
1. En Fabric, abre tu workspace y el Lakehouse `Gold_AnalyzeLoanV3_Target`.
2. Expande **Tables > dbo** (pulsa **Refresh** si no aparecen al instante):
   - `dim_loan`, `dim_prev_application`, `dim_relative_month`,
     `dim_dpd_bucket_v2`, `fact_pos_cash_monthly_balance_v2`.
3. Tambien puedes consultarlas desde el **SQL analytics endpoint**:
   ```sql
   SELECT TOP 10 * FROM dbo.dim_loan;
   ```

> Nota: esta via NO restaura la ontologia `AnalyzeLoanOnV3` (su definicion no esta
> en el repo). Cubre lakehouse + tablas, que es lo necesario para consultar los
> datos o conectarlos a un Data Agent.

## Crear un Data Agent sobre estas tablas

Una vez cargadas las tablas, puedes exponerlas a un **Data Agent** de Fabric para
consultarlas en lenguaje natural. El conjunto es un dataset de riesgo crediticio
estilo Home Credit: prestamos y su resultado (impago vs pagado), perfil del cliente,
solicitudes previas y el saldo mensual con morosidad.

Configura el agente segun los niveles descritos en la guia oficial
(https://learn.microsoft.com/en-us/fabric/data-science/data-agent-configurations).

### Description (proposito y capacidades, corto)
```
Credit-risk analytics agent for a Home Credit-style loan portfolio. Answers
natural-language questions about default risk, delinquency, borrower demographics,
loan amounts, and prior applications over the Gold lakehouse.
```

### Data agent instructions (nivel agente)
```markdown
## Objective
Help analysts explore loan/credit risk, customer profiles, prior applications,
and monthly repayment behavior for a Home Credit-style lending portfolio.
Answer questions about default risk, delinquency, demographics, and loan amounts.

## Data sources
Use the lakehouse "Gold_AnalyzeLoanV3_Target" (schema dbo) as the single source
of truth. It contains the loan master, previous applications, the monthly POS/cash
balance fact, and supporting dimensions for delinquency buckets and relative months.

## Key terminology
- "default", "impago", "bad loan" => target = 1 in dbo.dim_loan (1 = defaulted, 0 = repaid).
- "DPD" => days past due; column SK_DPD in dbo.fact_pos_cash_monthly_balance_v2.
- "delinquency bucket" => bucket_label in dbo.dim_dpd_bucket_v2 (no_dpd, dpd_1_30, ...).
- "loan amount" / "credit" => AMT_CREDIT; "income" => AMT_INCOME_TOTAL (in dbo.dim_loan).
- "previous application" / "prior application" => dbo.dim_prev_application.
- MONTHS_BALANCE is a negative integer counting months backward from a reference point.
- Monetary amounts use the dataset's original currency units; do not assume USD.

## Response guidelines
- Always state the exact filter used for "default" (target = 1) when reporting rates.
- Express rates as percentages and include the underlying counts (numerator/denominator).
- When aggregating money, round to 2 decimals and label the metric (avg, sum, median).
- If a question is ambiguous (e.g., "best customers"), ask what metric to rank by.
- Prefer joining on business keys (loan_id) unless a surrogate key (loan_sk) is required.

## Handling common topics
- Default/risk rates: compute from dbo.dim_loan using target.
- Delinquency over time: use dbo.fact_pos_cash_monthly_balance_v2 with SK_DPD and
  dbo.dim_dpd_bucket_v2 (join on sk_bucket), and dbo.dim_relative_month for time labels.
- "Rejected before": filter dbo.dim_prev_application where NAME_CONTRACT_STATUS = 'Refused'.
- Demographics: use dbo.dim_loan (CODE_GENDER, NAME_EDUCATION_TYPE, NAME_FAMILY_STATUS,
  OCCUPATION_TYPE, CNT_CHILDREN).
```

### Data source description (para el enrutado)
```markdown
Gold lakehouse "Gold_AnalyzeLoanV3_Target" with consumer-credit data:
loan applications and their outcome (default vs repaid), borrower demographics,
prior loan applications, and the monthly repayment/delinquency fact table.
Use it to answer default-risk, delinquency, demographic, loan-amount, and
prior-application questions. It does NOT contain marketing, web, or support-ticket data.
```

### Data source instructions (nivel fuente)
```markdown
## General knowledge
- One row per loan in dbo.dim_loan; target = 1 means the borrower defaulted.
- dbo.fact_pos_cash_monthly_balance_v2 is the grain = one row per loan per month.
- Join keys: loan_id links dim_loan <-> dim_prev_application <-> fact.
  Surrogate keys (loan_sk, prev_app_sk, relative_month_sk, sk_bucket) are also present.
- Many borrower columns may be empty/null; exclude nulls when averaging.

## Table descriptions
- dbo.dim_loan: loan + borrower profile. Key columns: loan_id, target,
  AMT_CREDIT, AMT_INCOME_TOTAL, AMT_ANNUITY, NAME_CONTRACT_TYPE, CODE_GENDER,
  FLAG_OWN_CAR, FLAG_OWN_REALTY, CNT_CHILDREN, NAME_EDUCATION_TYPE,
  NAME_FAMILY_STATUS, NAME_HOUSING_TYPE, OCCUPATION_TYPE, ORGANIZATION_TYPE,
  DAYS_BIRTH (negative days from reference), BirthYear.
- dbo.dim_prev_application: prior applications. Key columns: loan_id,
  NAME_CONTRACT_STATUS (Approved/Refused/Canceled/Unused offer), AMT_APPLICATION,
  AMT_CREDIT, NAME_CASH_LOAN_PURPOSE, NAME_CLIENT_TYPE, NAME_PRODUCT_TYPE.
- dbo.fact_pos_cash_monthly_balance_v2: monthly balance fact. Key columns:
  loan_id, MONTHS_BALANCE, SK_DPD, SK_DPD_DEF, NAME_CONTRACT_STATUS
  (Active/Completed/...), CNT_INSTALMENT, CNT_INSTALMENT_FUTURE, sk_bucket.
- dbo.dim_dpd_bucket_v2: sk_bucket -> bucket_label (no_dpd, dpd_1_30, ...).
- dbo.dim_relative_month: relative_month_sk -> relative_month_label (e.g. m-35);
  MONTHS_BALANCE is the join column to the fact.

## When asked about
- "default rate" or "impago": SELECT from dbo.dim_loan; rate = AVG(CAST(target AS FLOAT)).
- "delinquency buckets": join fact.sk_bucket = dim_dpd_bucket_v2.sk_bucket, group by bucket_label.
- "delinquency over time": join fact.MONTHS_BALANCE = dim_relative_month.MONTHS_BALANCE.
- "previously rejected customers": dbo.dim_prev_application WHERE NAME_CONTRACT_STATUS = 'Refused'.
- "active vs completed loans": group dbo.fact_pos_cash_monthly_balance_v2 by NAME_CONTRACT_STATUS.
- age: derive from BirthYear, or from DAYS_BIRTH/-365.25; DAYS_BIRTH is negative.
```

### Example queries (few-shot)
```sql
-- Q: What is the overall default rate?
SELECT CAST(SUM(target) AS FLOAT) / COUNT(*) AS default_rate, COUNT(*) AS total_loans
FROM dbo.dim_loan;
```
```sql
-- Q: Default rate by education level
SELECT NAME_EDUCATION_TYPE,
       COUNT(*) AS loans,
       SUM(target) AS defaults,
       CAST(SUM(target) AS FLOAT) / COUNT(*) AS default_rate
FROM dbo.dim_loan
GROUP BY NAME_EDUCATION_TYPE
ORDER BY default_rate DESC;
```
```sql
-- Q: Distribution of monthly balances by delinquency bucket
SELECT b.bucket_label,
       COUNT(*) AS monthly_records
FROM dbo.fact_pos_cash_monthly_balance_v2 f
JOIN dbo.dim_dpd_bucket_v2 b ON f.sk_bucket = b.sk_bucket
GROUP BY b.bucket_label
ORDER BY monthly_records DESC;
```

> El SQL anterior es T-SQL para el **SQL analytics endpoint** del lakehouse. Si
> conectas la fuente como semantic model (DAX) o KQL, reescribe los ejemplos en
> ese lenguaje.
