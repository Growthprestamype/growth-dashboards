"""
Procesador del proyecto "Puesta en Marcha LTV".

Replica la logica de la notebook (Puesta_en_Marcha_LTV.ipynb):

  - Proyeccion  -> Data_2025.csv : impacto ESPERADO a partir del historico.
  - Seguimiento -> Data_2026.csv : impacto REAL desde el lanzamiento (27-mar-2026).

Expone build() -> {"proyeccion": {...}, "seguimiento": {...}}.

Conteo de casos (identico a las celdas "Cantidad de Casos" de la notebook):
  - Casos elegibles  = "Es un caso"            (87 en 2025)
  - Cerrados         = caso & Marca Contrato   (84 en 2025)
  - Sin contrato     = caso & ~Marca Contrato  (3  en 2025)
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# permitir importar core.charts tanto en local como en Render
sys.path.append(str(Path(__file__).resolve().parents[2]))
from core.fechas import fecha_subida  # noqa: E402
from core.general import capas_para  # noqa: E402
from core.charts import bar_chart, increment_bars, line_chart  # noqa: E402

warnings.filterwarnings("ignore")

DATA_DIR = Path(__file__).resolve().parent / "data"
FECHA_LANZAMIENTO = "2026-03-27"

ZONAS_PROPUESTA = ["LIMA TOP", "LIMA MODERNA", "LIMA ESTE"]
ZONAS_PRINCIPALES = ["LIMA TOP", "LIMA MODERNA", "LOS OLIVOS (COMERCIAL)"]

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# --- Regla de negocio: LTV maximo por operacion ------------------------


def calcular_ltv_maximo(row):
    riesgo = str(row.get("Riesgo", "")).strip()
    zona = str(row.get("Sub zona", "")).strip().upper()
    tipo_fondo = str(row.get("Tipo de Fondo", "")).strip()
    esquema = str(row.get("Esquema", "")).strip()

    es_p2p = tipo_fondo == "Inversionista P2P"
    ltv = np.nan

    categoria_zona = "PRINCIPAL" if zona in ZONAS_PRINCIPALES else "OTROS"

    if riesgo in ["Bajo", "Bajo Medio"]:
        if categoria_zona == "PRINCIPAL":
            ltv = 0.55 if es_p2p else 0.50
        else:
            ltv = 0.45 if es_p2p else 0.40
    elif riesgo == "Moderado":
        if categoria_zona == "PRINCIPAL":
            ltv = 0.55 if es_p2p else 0.50
        else:
            ltv = 0.40
    elif riesgo == "Moderado Medio":
        ltv = 0.50 if categoria_zona == "PRINCIPAL" else 0.40
    elif riesgo == "Medio":
        ltv = 0.40 if categoria_zona == "PRINCIPAL" else 0.25
    elif riesgo == "Alto":
        if zona == "LIMA TOP":
            ltv = 0.35
        elif zona == "LIMA MODERNA":
            ltv = 0.30
        else:
            ltv = 0.15
        if esquema != "Cuota Fija":
            return np.nan

    if esquema != "Cuota Fija" and pd.notna(ltv) and ltv > 0.50:
        ltv = 0.50

    return ltv


# --- Helpers de formato (es-PE) ----------------------------------------


def soles(v, dec=0):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return "S/ " + f"{v:,.{dec}f}"


def millones(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"S/ {v / 1_000_000:,.2f} M"


def pct(v, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v * 100:,.{dec}f}%"


def num(v, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:,.{dec}f}"


def _mes(periodo):
    """202503 -> ('Mar', 2025)."""
    p = int(periodo)
    return MESES[(p % 100) - 1], p // 100


# --- Marcado comun de casos --------------------------------------------


def _marcar(df):
    df["LTV_Maximo"] = df.apply(calcular_ltv_maximo, axis=1)
    df["Marca_LTV"] = df["LTV_Maximo"] > df["LTV"]
    df["Marca Contrato"] = df["Codigo de Contrato"].isna() == False  # noqa: E712
    return df


def _serie_por_periodo(casos):
    """Agrupa los casos por 'Periodo de Cierre' y arma series por metrica."""
    rows = []
    for per, g in casos.groupby("Periodo de Cierre"):
        if pd.isna(per):
            continue
        cerr = g[g["Marca Contrato"]]
        n, nc = len(g), len(cerr)
        rows.append(
            {
                "per": int(per),
                "n": n,
                "nc": nc,
                "conv": (nc / n) if n else float("nan"),
                "vol": cerr["Monto Desembolsado Solarizado"].sum(),
                "ticket": cerr["Monto Desembolsado Solarizado"].mean(),
                "dias": g["Dias de Cierre"].mean(),
            }
        )
    rows.sort(key=lambda r: r["per"])
    return rows


def _bloque_evolucion(rows):
    """Construye los graficos SVG de evolucion a partir de las series."""
    if not rows:
        return None

    labels = [_mes(r["per"])[0] for r in rows]
    anio_ini = _mes(rows[0]["per"])[1]
    anio_fin = _mes(rows[-1]["per"])[1]
    rango = (f"{labels[0]} - {labels[-1]} {anio_fin}" if anio_ini == anio_fin
             else f"{labels[0]} {anio_ini} - {labels[-1]} {anio_fin}")

    vol_points = [
        {"label": labels[i], "value": r["vol"], "caption": f"{r['n']} casos"}
        for i, r in enumerate(rows)
    ]
    conv_v = [r["conv"] for r in rows]
    tick_v = [r["ticket"] for r in rows]
    dias_v = [r["dias"] for r in rows]

    return {
        "rango": rango,
        "vol_chart": bar_chart(
            vol_points,
            capas=capas_para([r["per"] for r in rows]),
            y_fmt=lambda v: f"{v / 1e6:.1f}M",
            tip_fmt=lambda v: soles(v),
        ),
        "series": [
            {"label": "Conversión",
             "svg": line_chart(labels, conv_v,
                               y_fmt=lambda v: pct(v, 0),
                               tip_fmt=lambda v: pct(v, 1))},
            {"label": "Ticket promedio",
             "svg": line_chart(labels, tick_v,
                               y_fmt=lambda v: f"S/{v / 1000:,.0f}k",
                               tip_fmt=lambda v: soles(v))},
            {"label": "Días de cierre",
             "svg": line_chart(labels, dias_v,
                               y_fmt=lambda v: f"{v:.0f}",
                               tip_fmt=lambda v: f"{num(v, 1)} días")},
        ],
    }


# --- Vistas ------------------------------------------------------------


def _proyeccion():
    df = _marcar(pd.read_csv(DATA_DIR / "Data_2025.csv").copy())
    df["Aplica"] = (
        (df["Esquema"] == "Cuota Fija")
        & (df["Sub zona"].isin(ZONAS_PROPUESTA))
        & (df["Situacion del credito"] == "RYA")
    )
    df["Es un caso"] = (df["Aplica"] & df["Marca_LTV"]) | (
        df["Aplica"] & (df["Detalle Excepcion"] == "Ratio > al permitido")
    )

    casos = df[df["Es un caso"]]
    cerrados = casos[casos["Marca Contrato"]]
    no_cerrados = casos[~casos["Marca Contrato"]]

    n_casos, n_cerr, n_noc = len(casos), len(cerrados), len(no_cerrados)
    conv = n_cerr / n_casos if n_casos else float("nan")

    vol_hist = cerrados["Monto Desembolsado Solarizado"].sum()
    vol_pot = vol_hist + no_cerrados["Monto Desembolsado Solarizado"].sum()
    ticket_cerr = cerrados["Monto Desembolsado Solarizado"].mean()
    ticket_gral = casos["Monto Desembolsado Solarizado"].mean()
    dias = casos["Dias de Cierre"].mean()

    return {
        "datos_hasta": fecha_subida(DATA_DIR / "Data_2025.csv"),
        "f": {
            "n_elegibles": f"{n_casos}",
            "n_cerrados": f"{n_cerr}",
            "n_no_cerrados": f"{n_noc}",
            "conv": pct(conv),
            "vol_hist": millones(vol_hist),
            "vol_pot": millones(vol_pot),
            "vol_hist_full": soles(vol_hist),
            "vol_pot_full": soles(vol_pot),
            "adicional": soles(vol_pot - vol_hist),
            "ticket_cerr": soles(ticket_cerr),
            "ticket_gral": soles(ticket_gral),
            "dias": num(dias),
        },
        "bar_pct": round(vol_hist / vol_pot * 100, 1) if vol_pot else 0,
        "inc_chart": increment_bars(vol_hist, vol_pot, fmt=lambda v: soles(v)),
        "uplift": pct((vol_pot - vol_hist) / vol_hist) if vol_hist else "-",
        "evol": _bloque_evolucion(_serie_por_periodo(casos)),
        "_raw": {"conv": conv, "ticket": ticket_cerr, "dias": dias},
    }


def _seguimiento(proy_raw):
    df = _marcar(pd.read_csv(DATA_DIR / "Data_2026.csv").copy())
    df["Fecha de Cierre"] = pd.to_datetime(df["Fecha de Cierre"])
    df["Marca_Lanzamiento"] = np.where(
        df["Fecha de Cierre"] >= FECHA_LANZAMIENTO, "Si", "No"
    )
    df["Aplica"] = (
        (df["Esquema"] == "Cuota Fija")
        & (df["Sub zona"].isin(ZONAS_PROPUESTA))
        & (df["Situacion del credito"] == "RYA")
        & (df["Marca_Lanzamiento"] == "Si")
    )
    df["Es un caso"] = (df["Aplica"] & df["Marca_LTV"]) | (
        df["Aplica"] & (df["Detalle Excepcion"] == "Ratio > al permitido")
    )

    casos = df[df["Es un caso"]]
    cerrados = casos[casos["Marca Contrato"]]
    no_cerrados = casos[~casos["Marca Contrato"]]

    n_casos, n_cerr, n_noc = len(casos), len(cerrados), len(no_cerrados)
    conv = n_cerr / n_casos if n_casos else float("nan")

    vol_cerr = cerrados["Monto Desembolsado Solarizado"].sum()
    ticket_cerr = cerrados["Monto Desembolsado Solarizado"].mean()
    ticket_gral = casos["Monto Desembolsado Solarizado"].mean()
    dias = casos["Dias de Cierre"].mean()

    def delta(real, esp):
        if esp in (None, 0) or (isinstance(esp, float) and np.isnan(esp)):
            return None
        return (real - esp) / esp

    return {
        "datos_hasta": fecha_subida(DATA_DIR / "Data_2026.csv"),
        "f": {
            "n_elegibles": f"{n_casos}",
            "n_cerrados": f"{n_cerr}",
            "n_no_cerrados": f"{n_noc}",
            "conv": pct(conv),
            "vol_cerr": millones(vol_cerr),
            "vol_cerr_full": soles(vol_cerr),
            "ticket_cerr": soles(ticket_cerr),
            "ticket_gral": soles(ticket_gral),
            "dias": num(dias),
        },
        "comp": [
            {"label": "Conversión", "esperado": pct(proy_raw["conv"]),
             "real": pct(conv), "delta": delta(conv, proy_raw["conv"]), "mejor": "alto"},
            {"label": "Ticket (cerrados)", "esperado": soles(proy_raw["ticket"]),
             "real": soles(ticket_cerr), "delta": delta(ticket_cerr, proy_raw["ticket"]),
             "mejor": "alto"},
            {"label": "Días de cierre", "esperado": num(proy_raw["dias"]),
             "real": num(dias), "delta": delta(dias, proy_raw["dias"]), "mejor": "bajo"},
        ],
        "evol": _bloque_evolucion(_serie_por_periodo(casos)),
    }


def build():
    proy = _proyeccion()
    seg = _seguimiento(proy.pop("_raw"))
    return {"proyeccion": proy, "seguimiento": seg}

