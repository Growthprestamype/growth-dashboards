"""
Contexto general del negocio, para superponerlo en los dashboards.

Lee una base anual unica y compartida (Data_anual.csv) y calcula, por mes
de cierre: casos, volumen desembolsado y ticket promedio. Con eso, cada
grafica de evolucion puede mostrar tres capas opcionales:

    fondo   Negocio general (casos del mes) en barras tenues, detras de
            la serie principal. Escala propia, a la derecha.
    marca   Ticket promedio del mes, como marca sobre las barras.
            Escala propia, a la derecha.
    base    Linea base: promedio del periodo de la serie principal
            (se calcula con los propios valores de la grafica).

El archivo vive en el origen externo, en la carpeta _general/, y se
sincroniza a datos_general/ igual que la data de cada proyecto. Si no
existe, las capas simplemente no aparecen: ningun dashboard se rompe.
"""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

import pandas as pd

from core import datos
from core.fechas import fecha_subida_dir

BASE_DIR = Path(__file__).resolve().parent.parent
CARPETA_ORIGEN = "_general"
DIR_LOCAL = BASE_DIR / "datos_general"
ARCHIVO = "Data_anual.csv"

# columnas esperadas (con alternativas por si el export cambia de nombre)
COL_PERIODO = "Periodo de Cierre"
COLS_MONTO = ["Monto Desembolsado Solarizado", "Monto Solarizado", "Monto"]
COL_CERRADO = "Flag Contrato Cerrado"
COL_CONTRATO = "Codigo de Contrato"

# Dimensiones del embudo. Cada una lista los nombres de columna que puede
# tener en el export; se muestra SOLO si alguna existe en Data_anual.csv.
# Asi, cuando el export sume una columna nueva (p. ej. "Tipo de Deuda" con
# NOR / RYA), el filtro aparece solo, sin tocar codigo.
DIMENSIONES_CANDIDATAS = [
    ("canal", ["Canal"], "Canal"),
    ("moneda", ["Moneda"], "Moneda"),
    ("esquema", ["Esquema"], "Esquema"),
    ("deuda", ["Tipo de Deuda", "Tipo Deuda", "Tipo de deuda", "Deuda",
               "Clasificacion Deuda", "Clasificación Deuda"], "Tipo de deuda"),
    ("fondo", ["Tipo de Fondo"], "Tipo de fondo"),
    ("riesgo", ["Riesgo"], "Riesgo"),
]

_cols_cache: tuple | None = None
_cols_firma = None


def dimensiones() -> list[tuple[str, str, str]]:
    """[(clave, columna, etiqueta)] de las dimensiones disponibles hoy."""
    global _cols_cache, _cols_firma
    p = ruta()
    if not p.exists():
        return []
    firma = (p.stat().st_mtime_ns, p.stat().st_size)
    if _cols_cache is not None and _cols_firma == firma:
        return list(_cols_cache)
    df = _leer()
    cols = set(df.columns) if df is not None else set()
    encontradas = []
    for clave, posibles, etiqueta in DIMENSIONES_CANDIDATAS:
        col = next((c for c in posibles if c in cols), None)
        if col:
            encontradas.append((clave, col, etiqueta))
    _cols_cache, _cols_firma = tuple(encontradas), firma
    return encontradas

# Los filtros del embudo viajan por contexto de request: los procesadores
# llaman a capas_para(periodos) sin saber nada de ellos.
_filtros: ContextVar[dict] = ContextVar("filtros_general", default={})

_cache: dict = {}
_cache_firma = None


def ruta() -> Path:
    return DIR_LOCAL / ARCHIVO


def sincronizar(forzar: bool = False) -> dict:
    """Trae Data_anual.csv del origen externo (carpeta _general/)."""
    return datos.sincronizar(CARPETA_ORIGEN, DIR_LOCAL, forzar=forzar)


def asegurar():
    datos.asegurar(CARPETA_ORIGEN, DIR_LOCAL)


def disponible() -> bool:
    return ruta().exists()


def fecha() -> str | None:
    return fecha_subida_dir(DIR_LOCAL)


def _leer() -> pd.DataFrame | None:
    p = ruta()
    if not p.exists():
        return None
    with open(p, encoding="utf-8", errors="ignore") as fh:
        primera = fh.readline()
    if ";" in primera and primera.count(";") > primera.count(","):
        df = pd.read_csv(p, sep=";", decimal=",")
    else:
        df = pd.read_csv(p)
    if len(df.columns) and str(df.columns[0]).startswith("Unnamed"):
        df = df.drop(columns=df.columns[0])
    return df


def filtros_actuales() -> dict:
    return dict(_filtros.get() or {})


def fijar_filtros(valores: dict | None):
    """Deja activos los filtros del embudo para este request."""
    limpio = {k: v for k, v in (valores or {}).items()
              if v and str(v).lower() not in ("", "todos", "todas")}
    _filtros.set(limpio)
    return limpio


def clave_filtros(valores: dict | None = None) -> str:
    """Firma corta para usar como parte de la clave de caché."""
    v = valores if valores is not None else filtros_actuales()
    return "|".join(f"{k}={v[k]}" for k in sorted(v)) or "todo"


def opciones() -> list[dict]:
    """Valores disponibles por dimensión, para armar el embudo."""
    df = _leer()
    salida = []
    for clave, col, etiqueta in dimensiones():
        vals = []
        if df is not None and col in df.columns:
            vals = sorted({str(x).strip() for x in df[col].dropna().unique()
                           if str(x).strip()})
        if vals:
            salida.append({"clave": clave, "etiqueta": etiqueta,
                           "valores": vals})
    return salida


def _filtrar(df, valores: dict):
    for clave, col, _ in dimensiones():
        elegido = valores.get(clave)
        if elegido and col in df.columns:
            df = df[df[col].astype(str).str.strip().str.lower()
                    == str(elegido).strip().lower()]
    return df


def serie_mensual(valores: dict | None = None) -> dict[int, dict]:
    """{202601: {casos, monto, ticket}} del negocio general, ya filtrado."""
    global _cache, _cache_firma
    p = ruta()
    if not p.exists():
        return {}
    firma = (p.stat().st_mtime_ns, p.stat().st_size)
    if _cache_firma != firma:
        _cache, _cache_firma = {}, firma
    activos = valores if valores is not None else filtros_actuales()
    ck = clave_filtros(activos)
    if ck in _cache:
        return _cache[ck]

    df = _leer()
    if df is None or COL_PERIODO not in df.columns:
        _cache[ck] = {}
        return {}
    df = _filtrar(df, activos)

    col_monto = next((c for c in COLS_MONTO if c in df.columns), None)

    # Universo: contratos efectivamente cerrados.
    if COL_CERRADO in df.columns:
        cerrados = df[df[COL_CERRADO].astype(str).str.upper().str.strip()
                      .isin(["SI", "SÍ", "TRUE", "1"])]
    elif COL_CONTRATO in df.columns:
        cerrados = df[df[COL_CONTRATO].notna()]
    else:
        cerrados = df
    cerrados = cerrados[pd.to_numeric(cerrados[COL_PERIODO],
                                      errors="coerce").notna()]

    salida: dict[int, dict] = {}
    for per, g in cerrados.groupby(cerrados[COL_PERIODO].astype(int)):
        casos = int(len(g))
        monto = float(g[col_monto].sum()) if col_monto else 0.0
        salida[int(per)] = {
            "casos": casos,
            "monto": monto,
            "ticket": (monto / casos) if casos else 0.0,
        }
    _cache[ck] = salida
    return salida


def _sufijo_filtros() -> str:
    v = filtros_actuales()
    partes = [v[k] for k, _, _ in dimensiones() if v.get(k)]
    return f" · {' · '.join(partes)}" if partes else ""


def capas_para(periodos) -> dict | None:
    """Capas alineadas a los periodos (YYYYMM) de una grafica.

    Devuelve None si no hay base anual o si no coincide ningun periodo,
    para que la grafica se dibuje igual que antes.
    """
    if not periodos:
        return None
    serie = serie_mensual()
    if not serie:
        return None

    casos, tickets = [], []
    for per in periodos:
        d = serie.get(int(per)) if per is not None else None
        casos.append(d["casos"] if d else None)
        tickets.append(d["ticket"] if d else None)

    if not any(c is not None for c in casos):
        return None

    suf = _sufijo_filtros()
    return {
        "fondo": {"clave": "fondo",
                  "nombre": f"Negocio general (casos){suf}",
                  "valores": casos, "unidad": "casos"},
        "marca": {"clave": "marca",
                  "nombre": f"Ticket promedio del mes{suf}",
                  "valores": tickets, "unidad": "soles"},
        "base": {"clave": "base", "nombre": "Línea base (promedio)"},
    }
