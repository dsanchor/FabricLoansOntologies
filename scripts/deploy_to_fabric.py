#!/usr/bin/env python3
"""
deploy_to_fabric.py
===================

Despliegue local y autonomo del Lakehouse Gold en un workspace de Microsoft
Fabric, SIN depender del workspace de origen (LoanDemoEnv).

Que hace, paso a paso:
  1. Lee la configuracion desde un archivo .env (ver .env.example).
  2. Se autentica contra Azure AD (interactive / device / az cli).
  3. Crea (o reutiliza) el Lakehouse destino via Fabric REST API.
  4. Extrae los ZIPs de tablas Delta incluidos en el repo.
  5. Sube cada tabla a OneLake bajo Tables/<schema>/<tabla>, de modo que
     Fabric la registre como tabla gestionada.

Uso:
    pip install -r scripts/requirements.txt
    cp .env.example .env          # y rellena los valores
    git lfs pull                  # IMPORTANTE: materializa los ZIPs reales
    python scripts/deploy_to_fabric.py            # despliegue completo
    python scripts/deploy_to_fabric.py --dry-run  # solo valida, no sube nada

Nota: la restauracion de la ontologia NO esta incluida (su definicion no esta
en el repo). Este script cubre lakehouse + tablas Gold.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import requests

# Las dependencias de Azure se importan de forma diferida para que --help y
# las validaciones basicas funcionen aunque aun no se haya hecho pip install.

REPO_ROOT = Path(__file__).resolve().parent.parent

FABRIC_API = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
ONELAKE_ACCOUNT_URL = "https://onelake.dfs.fabric.microsoft.com"
ONELAKE_SCOPE = "https://storage.azure.com/.default"

LFS_POINTER_MARKER = b"git-lfs.github.com/spec"


# --------------------------------------------------------------------------- #
# Configuracion
# --------------------------------------------------------------------------- #
class Config:
    def __init__(self) -> None:
        self.tenant_id = _require("FABRIC_TENANT_ID")
        self.auth_method = os.getenv("FABRIC_AUTH_METHOD", "interactive").strip().lower()
        self.workspace_id = _require("FABRIC_TARGET_WORKSPACE_ID")
        self.lakehouse_name = os.getenv(
            "FABRIC_TARGET_LAKEHOUSE_NAME", "Gold_AnalyzeLoanV3_Target"
        ).strip()
        self.create_if_missing = _as_bool(
            os.getenv("FABRIC_CREATE_LAKEHOUSE_IF_MISSING", "true")
        )
        self.enable_schemas = _as_bool(
            os.getenv("FABRIC_LAKEHOUSE_ENABLE_SCHEMAS", "true")
        )
        self.schema = os.getenv("FABRIC_TARGET_SCHEMA", "dbo").strip()
        self.zips_dir = (REPO_ROOT / os.getenv(
            "FABRIC_ZIPS_DIR", "data_snapshots/gold/zips"
        )).resolve()
        self.tables = [
            t.strip()
            for t in os.getenv(
                "FABRIC_TABLES",
                "dim_loan,dim_prev_application,dim_relative_month,"
                "dim_dpd_bucket_v2,fact_pos_cash_monthly_balance_v2",
            ).split(",")
            if t.strip()
        ]
        # Workdir temporal para extraer/convertir. Por defecto se usa el
        # filesystem local del sistema (tempfile), NO el repo, porque rutas
        # sincronizadas por OneDrive/montadas (/mnt/c/...) provocan errores
        # "Upload aborted" al escribir parquet con delta-rs.
        workdir_env = os.getenv("FABRIC_WORKDIR", "").strip()
        if workdir_env:
            self.workdir = (REPO_ROOT / workdir_env).resolve()
        else:
            self.workdir = (
                Path(tempfile.gettempdir()) / "fabric_deploy_workdir"
            ).resolve()

def _require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        _fail(
            f"Falta la variable obligatoria '{key}' en el .env. "
            "Copia .env.example a .env y rellena los valores."
        )
    return value


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "si", "on"}


def _fail(message: str) -> "None":
    print(f"\n[ERROR] {message}\n", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Autenticacion
# --------------------------------------------------------------------------- #
def build_credential(cfg: Config):
    try:
        from azure.identity import (
            AzureCliCredential,
            DeviceCodeCredential,
            InteractiveBrowserCredential,
        )
    except ImportError:
        _fail(
            "Falta el paquete azure-identity. Ejecuta:\n"
            "    pip install -r scripts/requirements.txt"
        )

    method = cfg.auth_method
    print(f"[auth] Metodo de autenticacion: {method}")
    if method == "cli":
        return AzureCliCredential(tenant_id=cfg.tenant_id)
    if method == "device":
        return DeviceCodeCredential(tenant_id=cfg.tenant_id)
    if method == "interactive":
        return InteractiveBrowserCredential(tenant_id=cfg.tenant_id)
    _fail(f"FABRIC_AUTH_METHOD invalido: '{method}'. Usa interactive | device | cli.")


def get_token(credential, scope: str) -> str:
    return credential.get_token(scope).token


# --------------------------------------------------------------------------- #
# Fabric REST: lakehouse
# --------------------------------------------------------------------------- #
def fabric_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def find_lakehouse(cfg: Config, token: str) -> dict | None:
    url = f"{FABRIC_API}/workspaces/{cfg.workspace_id}/items?type=Lakehouse"
    resp = requests.get(url, headers=fabric_headers(token), timeout=60)
    resp.raise_for_status()
    for item in resp.json().get("value", []):
        if item.get("displayName") == cfg.lakehouse_name:
            return item
    return None


def create_lakehouse(cfg: Config, token: str) -> dict:
    payload = {
        "displayName": cfg.lakehouse_name,
        "type": "Lakehouse",
        "creationPayload": {"enableSchemas": cfg.enable_schemas},
    }
    url = f"{FABRIC_API}/workspaces/{cfg.workspace_id}/items"
    resp = requests.post(url, headers=fabric_headers(token), json=payload, timeout=120)

    if resp.status_code == 202:  # operacion de larga duracion
        return _wait_lro_item(resp, cfg, token)
    resp.raise_for_status()
    return resp.json()


def _wait_lro_item(resp: requests.Response, cfg: Config, token: str) -> dict:
    location = resp.headers.get("Location") or resp.headers.get("location")
    if not location:
        _fail("Fabric acepto la creacion del lakehouse pero no devolvio 'Location'.")
    import time

    for _ in range(120):
        time.sleep(2)
        poll = requests.get(location, headers=fabric_headers(token), timeout=60)
        poll.raise_for_status()
        status = poll.json().get("status")
        if status == "Succeeded":
            break
        if status in ("Failed", "Canceled"):
            _fail(f"La creacion del lakehouse fallo: {poll.json()}")
    # Tras completarse, lo resolvemos por nombre.
    existing = find_lakehouse(cfg, token)
    if not existing:
        _fail("El lakehouse se creo pero no se pudo resolver su id.")
    return existing


def ensure_lakehouse(cfg: Config, token: str) -> dict:
    existing = find_lakehouse(cfg, token)
    if existing:
        print(f"[lakehouse] Reutilizando existente: {cfg.lakehouse_name} ({existing['id']})")
        return existing
    if not cfg.create_if_missing:
        _fail(
            f"El lakehouse '{cfg.lakehouse_name}' no existe y "
            "FABRIC_CREATE_LAKEHOUSE_IF_MISSING=false."
        )
    print(f"[lakehouse] Creando: {cfg.lakehouse_name} ...")
    created = create_lakehouse(cfg, token)
    print(f"[lakehouse] Creado: {cfg.lakehouse_name} ({created['id']})")
    return created


# --------------------------------------------------------------------------- #
# Extraccion de ZIPs
# --------------------------------------------------------------------------- #
def assert_real_zip(zip_path: Path) -> None:
    if not zip_path.exists():
        _fail(f"No existe el archivo: {zip_path}")
    with open(zip_path, "rb") as f:
        head = f.read(120)
    if LFS_POINTER_MARKER in head:
        _fail(
            f"'{zip_path.name}' es un puntero de Git LFS, no el dato real.\n"
            "Ejecuta primero:  git lfs pull"
        )
    if not zipfile.is_zipfile(zip_path):
        _fail(f"'{zip_path.name}' no es un ZIP valido.")


def extract_table_source(zip_path: Path, dest_dir: Path) -> Path:
    """Extrae el ZIP y devuelve una carpeta que contiene una tabla Delta lista
    para subir.

    Soporta dos formatos de origen dentro del ZIP:
      - Tabla Delta (contiene _delta_log)  -> se usa tal cual.
      - Un unico CSV exportado por Spark    -> se convierte a Delta localmente.
    """
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest_dir)

    # Caso 1: ya es una tabla Delta.
    for root, dirs, _ in os.walk(dest_dir):
        if "_delta_log" in dirs:
            return Path(root)

    # Caso 2: contiene CSV(s) -> convertir a Delta.
    csv_files = sorted(dest_dir.rglob("*.csv"))
    if csv_files:
        delta_dir = dest_dir.parent / (dest_dir.name + "_delta")
        _convert_csvs_to_delta(csv_files, delta_dir)
        return delta_dir

    _fail(
        f"El ZIP {zip_path.name} no contiene ni una tabla Delta (_delta_log) "
        "ni archivos CSV reconocibles."
    )


def _convert_csvs_to_delta(csv_files: list[Path], delta_dir: Path) -> None:
    """Lee uno o varios CSV (mismo esquema) y los escribe como tabla Delta
    local usando delta-rs (sin Spark)."""
    try:
        import pyarrow as pa  # noqa: F401
        from pyarrow import csv as pacsv
        from deltalake import write_deltalake
    except ImportError:
        _fail(
            "Faltan dependencias para convertir CSV a Delta. Ejecuta:\n"
            "    pip install -r scripts/requirements.txt"
        )

    if delta_dir.exists():
        shutil.rmtree(delta_dir)

    # Lee todos los CSV (Spark suele exportar uno solo, pero soportamos varios).
    convert_opts = pacsv.ConvertOptions(strings_can_be_null=True)
    tables = [pacsv.read_csv(str(p), convert_options=convert_opts) for p in csv_files]
    if len(tables) == 1:
        table = tables[0]
    else:
        import pyarrow as pa

        table = pa.concat_tables(tables, promote_options="default")

    write_deltalake(str(delta_dir), table, mode="overwrite")


# --------------------------------------------------------------------------- #
# OneLake: subida de la tabla
# --------------------------------------------------------------------------- #
def build_onelake_client(credential):
    try:
        from azure.storage.filedatalake import DataLakeServiceClient
    except ImportError:
        _fail(
            "Falta azure-storage-file-datalake. Ejecuta:\n"
            "    pip install -r scripts/requirements.txt"
        )
    return DataLakeServiceClient(account_url=ONELAKE_ACCOUNT_URL, credential=credential)


def upload_delta_table(
    service_client,
    cfg: Config,
    lakehouse_id: str,
    table_name: str,
    delta_root: Path,
) -> int:
    """Sube todos los archivos de la tabla Delta a
    OneLake://<workspace>/<lakehouse>/Tables/<schema>/<table>."""
    file_system = service_client.get_file_system_client(cfg.workspace_id)

    if cfg.enable_schemas:
        base_dir = f"{lakehouse_id}/Tables/{cfg.schema}/{table_name}"
    else:
        base_dir = f"{lakehouse_id}/Tables/{table_name}"

    uploaded = 0
    files = [p for p in delta_root.rglob("*") if p.is_file()]
    for local_file in files:
        rel = local_file.relative_to(delta_root).as_posix()
        remote_path = f"{base_dir}/{rel}"
        file_client = file_system.get_file_client(remote_path)
        with open(local_file, "rb") as data:
            file_client.upload_data(data, overwrite=True)
        uploaded += 1
    return uploaded


# --------------------------------------------------------------------------- #
# Orquestacion
# --------------------------------------------------------------------------- #
def run(cfg: Config, dry_run: bool) -> None:
    print("=" * 70)
    print("Despliegue Gold -> Fabric")
    print(f"  Workspace destino : {cfg.workspace_id}")
    print(f"  Lakehouse destino : {cfg.lakehouse_name}")
    print(f"  Esquema           : {cfg.schema} (schemas={cfg.enable_schemas})")
    print(f"  Tablas            : {', '.join(cfg.tables)}")
    print(f"  ZIPs              : {cfg.zips_dir}")
    print(f"  Modo              : {'DRY-RUN (no sube nada)' if dry_run else 'DESPLIEGUE'}")
    print("=" * 70)

    # 1) Validar que los ZIPs son datos reales (no punteros LFS).
    for table in cfg.tables:
        assert_real_zip(cfg.zips_dir / f"{table}.zip")
    print(f"[ok] {len(cfg.tables)} ZIPs validados (datos reales, no punteros LFS).")

    if dry_run:
        print("\n[dry-run] Validacion superada. No se ha contactado a Fabric.")
        return

    # 2) Autenticacion.
    credential = build_credential(cfg)
    fabric_token = get_token(credential, FABRIC_SCOPE)
    print("[auth] Token de Fabric obtenido.")

    # 3) Lakehouse destino.
    lakehouse = ensure_lakehouse(cfg, fabric_token)
    lakehouse_id = lakehouse["id"]

    # 4) OneLake client.
    onelake = build_onelake_client(credential)

    # 5) Subir cada tabla.
    results = []
    for table in cfg.tables:
        print(f"\n[tabla] {table}")
        zip_path = cfg.zips_dir / f"{table}.zip"
        work = cfg.workdir / table
        delta_root = extract_table_source(zip_path, work)
        print(f"  preparada (Delta) en: {delta_root}")
        n = upload_delta_table(onelake, cfg, lakehouse_id, table, delta_root)
        print(f"  subidos {n} archivos a Tables/{cfg.schema}/{table}")
        results.append((table, n))

    # Limpieza del workdir temporal.
    if cfg.workdir.exists():
        shutil.rmtree(cfg.workdir, ignore_errors=True)

    print("\n" + "=" * 70)
    print("Despliegue completado:")
    for table, n in results:
        print(f"  - {cfg.schema}.{table}: {n} archivos")
    print("=" * 70)
    print(
        "\nSiguiente paso: abre el Lakehouse en Fabric y refresca 'Tables'. "
        "Las tablas deberian aparecer en pocos segundos."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Despliega el Lakehouse Gold en Fabric desde los ZIPs del repo."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida configuracion y ZIPs sin contactar a Fabric ni subir datos.",
    )
    parser.add_argument(
        "--env-file",
        default=str(REPO_ROOT / ".env"),
        help="Ruta al archivo .env (por defecto: .env en la raiz del repo).",
    )
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(args.env_file)
    except ImportError:
        # python-dotenv es opcional; si no esta, se usan las variables de entorno.
        if not os.path.exists(args.env_file):
            print(
                "[warn] python-dotenv no instalado y no se uso .env; "
                "se leeran variables de entorno del sistema."
            )

    cfg = Config()
    run(cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
