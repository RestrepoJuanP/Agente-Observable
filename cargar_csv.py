"""Construya el suyo: lleva un CSV a una base SQLite y escribe el borrador de su capa semántica.

    python cargar_csv.py datos/contratos.csv --tabla contratos
    python cargar_csv.py datos/contratos.csv --tabla contratos --excluir proveedor_id,persona

Crea (o reemplaza) la tabla en datos/mia.sqlite y escribe datos/mi_capa.json con cada columna
marcada «COMPLETE»: el código adivina el tipo y un ejemplo; lo que significa cada columna
lo escribe usted. Las columnas de --excluir quedan en la base pero NO en la capa: para el
agente no existen y el guardián no deja leerlas.

Después, en .env:
    AURORA_DB=datos/mia.sqlite
    AURORA_CAPA=datos/mi_capa.json
"""
import argparse
import csv
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def tipo(valores: list[str]) -> str:
    llenos = [v for v in valores if v != ""]
    if llenos and all(re.fullmatch(r"-?\d+", v) for v in llenos):
        return "INTEGER"
    if llenos and all(re.fullmatch(r"-?\d+(\.\d+)?", v) for v in llenos):
        return "REAL"
    return "TEXT"


def convertir(v: str, t: str):
    if v == "":
        return None
    return int(v) if t == "INTEGER" else float(v) if t == "REAL" else v


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("csv", type=Path)
    a.add_argument("--tabla", required=True, help="Nombre de la tabla (minúsculas, sin espacios)")
    a.add_argument("--base", type=Path, default=RAIZ / "datos" / "mia.sqlite")
    a.add_argument("--capa", type=Path, default=RAIZ / "datos" / "mi_capa.json")
    a.add_argument("--excluir", default="", help="Columnas que el agente NO podrá leer, separadas por coma")
    a.add_argument("--separador", default=",")
    args = a.parse_args()

    if not re.fullmatch(r"[a-z_][a-z0-9_]*", args.tabla):
        raise SystemExit("--tabla: use minúsculas, números y guion bajo (por ejemplo contratos_2026)")
    with args.csv.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.reader(f, delimiter=args.separador))
    if len(filas) < 2:
        raise SystemExit("El CSV no tiene filas de datos.")
    encabezado = [re.sub(r"\W+", "_", c.strip().lower()).strip("_") or f"col{k}" for k, c in enumerate(filas[0])]
    datos = [f for f in filas[1:] if len(f) == len(encabezado)]
    descartadas = len(filas) - 1 - len(datos)
    tipos = [tipo([f[k] for f in datos]) for k in range(len(encabezado))]
    excluir = {c.strip().lower() for c in args.excluir.split(",") if c.strip()}
    if faltan := excluir - set(encabezado):
        raise SystemExit(f"--excluir: no existen {', '.join(sorted(faltan))}. Columnas: {', '.join(encabezado)}")

    args.base.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.base) as db:
        db.execute(f"DROP TABLE IF EXISTS {args.tabla}")
        db.execute(f"CREATE TABLE {args.tabla}(" + ", ".join(f"{c} {t}" for c, t in zip(encabezado, tipos)) + ")")
        db.executemany(f"INSERT INTO {args.tabla} VALUES ({','.join('?' * len(encabezado))})",
                       [[convertir(v, t) for v, t in zip(f, tipos)] for f in datos])

    print(f"\n{args.tabla}: {len(datos):,} filas · {len(encabezado)} columnas → {args.base.name}".replace(",", "."))
    if descartadas:
        print(f"  ! {descartadas} filas descartadas por tener otro número de columnas (revise comas dentro del texto)")
    print(f"\n  {'columna':<22} {'tipo':<8} {'vacías':>7} {'distintos':>10}  ejemplo")
    columnas = {}
    for k, (c, t) in enumerate(zip(encabezado, tipos)):
        vals = [f[k] for f in datos]
        ejemplo = next((v for v in vals if v), "")[:40]
        marca = "  ✕ excluida" if c in excluir else ""
        print(f"  {c:<22} {t:<8} {vals.count(''):>7} {len(set(vals)):>10}  {ejemplo}{marca}")
        if c not in excluir:
            columnas[c] = f"COMPLETE: qué significa. Tipo {t}. Ejemplo: {ejemplo}"

    capa = {
        "version": "0.1",
        "fuente": f"{args.csv.name} · cargado con cargar_csv.py. Lo que no está aquí no se puede leer.",
        "limite_filas": 50,
        "corte": date.today().isoformat(),
        "relaciones": [],
        "tablas": {
            args.tabla: {
                "descripcion": "COMPLETE: qué es una fila de esta tabla (por ejemplo, «un contrato firmado»).",
                "columnas": columnas,
                "reglas": ["COMPLETE: una regla del negocio que un recién llegado no adivinaría."],
                "ejemplos": [{"pregunta": f"¿Cuántas filas tiene {args.tabla}?", "sql": f"SELECT COUNT(*) AS n FROM {args.tabla}"}],
            }
        },
    }
    if args.capa.exists():
        previa = json.loads(args.capa.read_text(encoding="utf-8"))
        previa["tablas"][args.tabla] = capa["tablas"][args.tabla]
        capa = previa
    args.capa.write_text(json.dumps(capa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nCapa en borrador → {args.capa.relative_to(RAIZ) if args.capa.is_relative_to(RAIZ) else args.capa}")
    print("Siguiente: abra ese archivo y reemplace cada «COMPLETE» por lo que la columna significa de verdad.\n")


if __name__ == "__main__":
    main()
