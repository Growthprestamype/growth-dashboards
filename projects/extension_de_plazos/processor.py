"""
Procesador del proyecto "Extensión de Plazos para perfiles seguros".

Replica la logica de la notebook (Puesta_en_Marcha_Extension.ipynb):

  - Proyeccion  -> Data_2025.csv : impacto ESPERADO a partir del historico.
  - Seguimiento -> Data_2026.csv : impacto REAL desde el lanzamiento (26-may-2026).

La propuesta: extender el plazo de credito para perfiles seguros (zonas Lima
top/moderna/este, riesgo homologado A+/A/B, canal Digital, plazo > 72 meses).
Algunos clientes elegibles no cerraron por motivos atendibles (plazos muy
cortos, competencia, demora, otros): son los casos "recuperables" que la
extension de plazos buscaria capturar.

Conteo de casos (celdas "Cantidad de Casos" de la notebook, base 2025):
  - Segmento elegible = "Aplica propuesta"                 (24)
  - Cerrados          = elegible & con contrato            (20)
  - Recuperables      = elegible & sin contrato & motivo   (1)
  - Potencial         = cerrados + recuperables            (21)
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
FECHA_LANZAMIENTO = "2026-05-26"

ZONAS_PROPUESTA = ["LIMA TOP", "LIMA MODERNA", "LIMA ESTE"]
RIESGOS_SEGUROS = ["A+", "A", "B"]
PLAZO_MINIMO = 72
MOTIVOS_RECUPERABLES = [
    "OTROS",
    "YA OPTO POR LA COMPETENCIA",
    "PROCESO DEMORA MUCHO",
    "PLAZOS DE PRESTAMO MUY CORTOS",
]
MDS = "Monto Desembolsado Solarizado"

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


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
    """202506 -> ('Jun', 2025)."""
    p = int(periodo)
    return MESES[(p % 100) - 1], p // 100


# --- Marcado comun -----------------------------------------------------


def _marcar(df):
    df["Marca Contrato"] = df["Codigo de Contrato"].isna() == False  # noqa: E712
    return df


def _serie_por_periodo(elegibles):
    """Agrupa el segmento elegible por 'Periodo de Cierre' y arma series."""
    rows = []
    for per, g in elegibles.groupby("Periodo de Cierre"):
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
                "vol": cerr[MDS].sum(),
                "ticket": cerr[MDS].mean(),
                "dias": cerr["Dias de Cierre"].mean(),
            }
        )
    rows.sort(key=lambda r: r["per"])
    return rows


def _bloque_evolucion(rows):
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
        df["Sub zona"].isin(ZONAS_PROPUESTA)
        & df["Riesgo homologado"].isin(RIESGOS_SEGUROS)
        & (df["Canal"] == "Digital")
        & (df["Plazo"] > PLAZO_MINIMO)
    )
    df["Recuperable"] = (
        df["Aplica"]
        & df["Codigo de Contrato"].isna()
        & df["Motivo de rechazo (NO ESTA INTERESADO)"].isin(MOTIVOS_RECUPERABLES)
    )

    elegibles = df[df["Aplica"]]
    cerrados = elegibles[elegibles["Marca Contrato"]]
    recuperables = df[df["Recuperable"]]

    n_apl, n_cerr, n_rec = len(elegibles), len(cerrados), len(recuperables)
    n_pot = n_cerr + n_rec
    conv = n_cerr / n_apl if n_apl else float("nan")
    conv_pot = n_pot / n_apl if n_apl else float("nan")

    vol_hist = cerrados[MDS].sum()
    vol_pot = vol_hist + recuperables[MDS].sum()
    ticket = cerrados[MDS].mean()
    dias = cerrados["Dias de Cierre"].mean()

    return {
        "datos_hasta": fecha_subida(DATA_DIR / "Data_2025.csv"),
        "f": {
            "n_elegibles": f"{n_apl}",
            "n_cerrados": f"{n_cerr}",
            "n_recuperables": f"{n_rec}",
            "conv": pct(conv),
            "conv_pot": pct(conv_pot),
            "ticket": soles(ticket),
            "dias": num(dias),
            "vol_hist_full": soles(vol_hist),
            "vol_pot_full": soles(vol_pot),
            "adicional": soles(vol_pot - vol_hist),
        },
        "inc_chart": increment_bars(vol_hist, vol_pot, fmt=lambda v: soles(v)),
        "uplift": pct((vol_pot - vol_hist) / vol_hist) if vol_hist else "-",
        "evol": _bloque_evolucion(_serie_por_periodo(elegibles)),
        "_raw": {"conv": conv, "ticket": ticket, "dias": dias},
    }


def _seguimiento(proy_raw):
    df = _marcar(pd.read_csv(DATA_DIR / "Data_2026.csv").copy())
    df["Fecha de Cierre"] = pd.to_datetime(df["Fecha de Cierre"])
    df["Marca_Lanzamiento"] = np.where(
        df["Fecha de Cierre"] >= FECHA_LANZAMIENTO, "Si", "No"
    )
    df["Aplica"] = (
        (df["Marca_Lanzamiento"] == "Si")
        & df["Sub zona"].isin(ZONAS_PROPUESTA)
        & df["Riesgo homologado"].isin(RIESGOS_SEGUROS)
    )

    elegibles = df[df["Aplica"]]
    cerrados = elegibles[elegibles["Marca Contrato"]]

    n_apl, n_cerr = len(elegibles), len(cerrados)
    conv = n_cerr / n_apl if n_apl else float("nan")

    vol_cerr = cerrados[MDS].sum()
    ticket = cerrados[MDS].mean()
    dias = cerrados["Dias de Cierre"].mean()

    def delta(real, esp):
        if esp in (None, 0) or (isinstance(esp, float) and np.isnan(esp)):
            return None
        return (real - esp) / esp

    return {
        "datos_hasta": fecha_subida(DATA_DIR / "Data_2026.csv"),
        "f": {
            "n_elegibles": f"{n_apl}",
            "n_cerrados": f"{n_cerr}",
            "conv": pct(conv),
            "vol_cerr": millones(vol_cerr),
            "vol_cerr_full": soles(vol_cerr),
            "ticket": soles(ticket),
            "dias": num(dias),
        },
        "comp": [
            {"label": "Conversión", "esperado": pct(proy_raw["conv"]),
             "real": pct(conv), "delta": delta(conv, proy_raw["conv"]),
             "mejor": "alto"},
            {"label": "Ticket promedio", "esperado": soles(proy_raw["ticket"]),
             "real": soles(ticket), "delta": delta(ticket, proy_raw["ticket"]),
             "mejor": "alto"},
            {"label": "Días de cierre", "esperado": num(proy_raw["dias"]),
             "real": num(dias), "delta": delta(dias, proy_raw["dias"]),
             "mejor": "bajo"},
        ],
        "evol": _bloque_evolucion(_serie_por_periodo(elegibles)),
    }


def build():
    proy = _proyeccion()
    seg = _seguimiento(proy.pop("_raw"))
    return {"proyeccion": proy, "seguimiento": seg}

