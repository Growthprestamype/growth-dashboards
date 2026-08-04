"""
Procesador del proyecto "Descuento en tasas".

A diferencia de los otros experimentos, este consume la DATA DE SALIDA de las
notebooks (Proyeccion_Final.ipynb / Seguimiento_Final_VF.ipynb), que ya traen
las columnas calculadas contra el tarifario (proceso que corre en Excel y por
eso no se traslada aqui). Para actualizar el dashboard basta con reemplazar:

    data/Data_Historica.csv    (export: sep=';', decimal=',')
    data/Data_Seguimiento.csv  (export: sep=';', decimal=',')

La propuesta: aplicar un descuento en tasas a operaciones P2P del canal
Digital. La metrica central es la COMISION (recaudacion), no el volumen.

Definiciones (heredadas de la notebook):
  Proyeccion (base 2025, contratos cerrados):
    - Caso              = "Es Caso en Historico" (P2P & Digital)          567
    - Comision Proyectada = Ratio_Comision_Real_Ideal x comision ideal
                            con descuento (ya viene calculada)
    - Adicional         = Comision Proyectada - Comision
  Seguimiento (2026, lanzamiento 15-may-2026):
    - Caso              = "Condicion Fuerte es Caso en Seguimiento"
                          (la comision cobrada cae en el dominio del
                          tarifario con descuento)
    - Esperada          = "AJUSTADA COMISION SD. NO FT MONTO IDEAL"
                          (lo que se habria cobrado sin la propuesta)
    - Adicional         = Comision - Esperada
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[2]))
from core.fechas import fecha_subida  # noqa: E402
from core.general import capas_para  # noqa: E402
from core.charts import dual_bar_chart, increment_bars, line_chart  # noqa: E402

warnings.filterwarnings("ignore")

DATA_DIR = Path(__file__).resolve().parent / "data"
FECHA_LANZAMIENTO = "15 may 2026"

COL_ESPERADA = "AJUSTADA COMISION SD. NO FT MONTO IDEAL"
COL_CASO_SEG = "Condicion Fuerte es Caso en Seguimiento"

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


def miles(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"S/ {v / 1000:,.2f} mil"


def pct(v, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v * 100:,.{dec}f}%"


def num(v, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:,.{dec}f}"


def _mes(periodo):
    p = int(periodo)
    return MESES[(p % 100) - 1], p // 100


def _rango(rows):
    labels = [_mes(r["per"])[0] for r in rows]
    a0, a1 = _mes(rows[0]["per"])[1], _mes(rows[-1]["per"])[1]
    return (f"{labels[0]} - {labels[-1]} {a1}" if a0 == a1
            else f"{labels[0]} {a0} - {labels[-1]} {a1}")


def _leer(nombre):
    """Los exports de la notebook vienen con sep=';' y decimal=','."""
    return pd.read_csv(DATA_DIR / nombre, sep=";", decimal=",")


# --- Evolucion (comision real vs. proyectada/esperada) ------------------


def _bloque_evolucion(rows, name_a, name_b, en_miles=False):
    if not rows:
        return None

    labels = [_mes(r["per"])[0] for r in rows]
    y_fmt = ((lambda v: f"{v / 1000:,.0f}k") if en_miles
             else (lambda v: f"{v / 1e6:.1f}M"))

    points = [
        {"label": labels[i], "a": r["com_a"], "b": r["com_b"],
         "caption": f"{r['n']} casos"}
        for i, r in enumerate(rows)
    ]

    series = [
        {"label": "Casos",
         "svg": line_chart(labels, [r["n"] for r in rows],
                           y_fmt=lambda v: f"{v:.0f}",
                           tip_fmt=lambda v: f"{v:.0f} casos")},
        {"label": "Comisión adicional por caso",
         "svg": line_chart(labels, [r["adic_caso"] for r in rows],
                           y_fmt=lambda v: f"S/{v / 1000:,.1f}k",
                           tip_fmt=lambda v: soles(v))},
        {"label": "Recaudación adicional del mes",
         "svg": line_chart(labels, [r["adic"] for r in rows],
                           y_fmt=lambda v: f"S/{v / 1000:,.0f}k",
                           tip_fmt=lambda v: soles(v))},
    ]

    return {
        "rango": _rango(rows),
        "vol_title": "Comisión por mes",
        "vol_unit": f"{name_a} vs. {name_b}, soles",
        "vol_chart": dual_bar_chart(
            points,
            capas=capas_para([r["per"] for r in rows]),
            y_fmt=y_fmt,
            tip_fmt=lambda v: soles(v),
            name_a=name_a,
            name_b=name_b,
        ),
        "series": series,
    }


# --- Vistas ------------------------------------------------------------


def _proyeccion():
    df = _leer("Data_Historica.csv")
    casos = df[df["Es Caso en Historico"] == True].copy()  # noqa: E712
    casos["adic"] = casos["Comision Proyectada"] - casos["Comision"]

    n_casos, n_total = len(casos), len(df)
    com_hist = casos["Comision"].sum()
    com_proy = casos["Comision Proyectada"].sum()
    adicional = com_proy - com_hist

    # series mensuales del segmento
    rows = []
    for per, g in casos.groupby("Periodo de Cierre"):
        if pd.isna(per):
            continue
        rows.append({
            "per": int(per),
            "n": len(g),
            "com_a": g["Comision"].sum(),
            "com_b": g["Comision Proyectada"].sum(),
            "adic": g["adic"].sum(),
            "adic_caso": g["adic"].mean(),
        })
    rows.sort(key=lambda r: r["per"])

    n_mes = [r["n"] for r in rows]
    adic_caso_mes = [r["adic_caso"] for r in rows]

    # cotas de escenario mensual: combina el mes de menor (mayor) adicional
    # por caso con el mes de menos (mas) casos, tal como en la plantilla.
    esc_min = min(adic_caso_mes) * min(n_mes) if rows else float("nan")
    esc_max = max(adic_caso_mes) * max(n_mes) if rows else float("nan")

    meses_n = len(rows)

    # --- estadisticos mensuales del historico (referencias del seguimiento)
    adic_mes = [r["adic"] for r in rows]
    ratio_mes = [g["Ratio Comision/Monto"].mean()
                 for _, g in casos.groupby("Periodo de Cierre")]
    tasa_mensual = df.groupby("Periodo de Cierre")["Es Caso en Historico"].mean()

    def _stats(vals):
        if not vals:
            return {"min": float("nan"), "prom": float("nan"), "max": float("nan")}
        return {"min": min(vals), "prom": sum(vals) / len(vals), "max": max(vals)}

    # --- panorama global por canal (Digital por defecto en la vista)
    per_n = df["Periodo de Cierre"].nunique() or 1
    global_por_canal = {}
    for clave, sub in [("digital", df[df["Canal"] == "Digital"]),
                       ("presencial", df[df["Canal"] == "Presencial"]),
                       ("todos", df)]:
        sub_casos = sub[sub["Es Caso en Historico"] == True]  # noqa: E712
        global_por_canal[clave] = {
            "cerrados": f"{len(sub):,}",
            "cerrados_mes": f"{len(sub) / per_n:,.0f}",
            "com_caso": soles(sub["Comision"].mean()) if len(sub) else "-",
            "com_total": millones(sub["Comision"].sum()),
            "dias": num(sub["Dias de Cierre"].mean()) if len(sub) else "-",
            "tasa": pct(len(sub_casos) / len(sub)) if len(sub) else "-",
        }

    return {
        "datos_hasta": fecha_subida(DATA_DIR / "Data_Historica.csv"),
        "f": {
            "n_casos": f"{n_casos}",
            "com_caso": soles(casos["Comision"].mean()),
            "com_total": millones(com_hist),
            "dias": num(casos["Dias de Cierre"].mean()),
            "adic_caso": soles(casos["adic"].mean()),
            "adicional": soles(adicional),
            "com_hist_full": soles(com_hist),
            "com_proy_full": soles(com_proy),
            # panorama global 2025 (todos los contratos cerrados)
            "g_cerrados": f"{n_total:,}",
            "g_cerrados_mes": num(n_total / meses_n, 0) if meses_n else "-",
            "g_com_caso": soles(df["Comision"].mean()),
            "g_com_total": millones(df["Comision"].sum()),
            "g_dias": num(df["Dias de Cierre"].mean()),
            "g_tasa_casos": pct(n_casos / n_total) if n_total else "-",
            "g_ratio": num(casos["Ratio Comision/Monto"].mean(), 2),
            # cotas mensuales
            "r_adic_caso": f"{soles(min(adic_caso_mes))} – {soles(max(adic_caso_mes))}",
            "r_casos": f"{min(n_mes)} – {max(n_mes)}",
            "r_casos_prom": num(sum(n_mes) / meses_n, 1) if meses_n else "-",
            "r_recaud": f"{miles(esc_min)} – {miles(esc_max)}",
        },
        "g": global_por_canal,
        "inc_chart": increment_bars(com_hist, com_proy, fmt=lambda v: soles(v),
                                    label_a="Histórica", label_b="Proyectada"),
        "uplift": pct(adicional / com_hist) if com_hist else "-",
        "evol": _bloque_evolucion(rows, "Comisión real", "Comisión proyectada"),
        "_raw": {
            "com_esp_tag": "esperada",
            "refs": {
                "adic_caso": _stats(adic_caso_mes),
                "casos_mes": _stats([float(n) for n in n_mes]),
                "adic_mes": _stats(adic_mes),
                "ratio": _stats(ratio_mes),
                "tasa_anual": n_casos / n_total if n_total else float("nan"),
                "tasa_prom_mensual": float(tasa_mensual.mean()),
            },
        },
    }


def _seguimiento(proy_raw):
    df = _leer("Data_Seguimiento.csv")
    post = df[df["Marca_15_Mayo_Cierre"] == "Sí"].copy()
    casos = post[post[COL_CASO_SEG] == True].copy()  # noqa: E712
    casos["adic"] = casos["Comision"] - casos[COL_ESPERADA]

    n_casos = len(casos)
    com_real = casos["Comision"].sum()
    com_esp = casos[COL_ESPERADA].sum()
    adicional = com_real - com_esp

    rows = []
    for per, g in casos.groupby("Periodo de Cierre"):
        if pd.isna(per):
            continue
        rows.append({
            "per": int(per),
            "n": len(g),
            "com_a": g[COL_ESPERADA].sum(),
            "com_b": g["Comision"].sum(),
            "adic": g["adic"].sum(),
            "adic_caso": g["adic"].mean(),
        })
    rows.sort(key=lambda r: r["per"])
    meses_n = len(rows) or 1

    # tasa de casos P2P-Digital por mes (sobre cierres post-lanzamiento)
    tasa_mes = post.groupby("Periodo de Cierre")["Es Caso en Seguimiento"].mean()
    tasa_real = tasa_mes.mean() if len(tasa_mes) else float("nan")
    ratio_real = casos["Ratio Comision/Monto"].mean()

    # cierres globales por mes: meses calendario completos con casos
    pers = [r["per"] for r in rows]
    glob = df[df["Periodo de Cierre"].isin(pers)]
    cerrados_mes = len(glob) / meses_n

    adic_caso_real = casos["adic"].mean()
    casos_mes_real = n_casos / meses_n
    adic_mes_real = adicional / meses_n

    def delta(real, esp):
        if esp in (None, 0) or (isinstance(esp, float) and np.isnan(esp)):
            return None
        return (real - esp) / esp

    refs = proy_raw["refs"]

    def fila(label, formula, real_num, real_fmt, opciones, default=0,
             mejor="alto", tag_ref="Referencia"):
        base = float(opciones[default]["num"])
        d = ((float(real_num) - base) / abs(base)) if base else None
        return {"label": label, "formula": formula, "real": real_fmt,
                "real_num": float(real_num), "opciones": opciones,
                "default": default, "delta": d, "mejor": mejor,
                "tag_ref": tag_ref}

    def ops(st, fmt):
        return [
            {"id": "prom", "label": "promedio 2025", "num": st["prom"], "fmt": fmt(st["prom"])},
            {"id": "min", "label": "mínimo", "num": st["min"], "fmt": fmt(st["min"])},
            {"id": "max", "label": "máximo", "num": st["max"], "fmt": fmt(st["max"])},
        ]

    comp = [
        fila("Comisión total del segmento",
             "comisión cobrada vs. la que se esperaba cobrar sin el ajuste",
             com_real, miles(com_real),
             [{"id": "esp", "label": "esperada", "num": com_esp, "fmt": miles(com_esp)}],
             tag_ref="Esperado"),
        fila("Comisión adicional por caso",
             "comisión cobrada − comisión que se esperaba cobrar sin el ajuste, por caso",
             adic_caso_real, soles(adic_caso_real),
             ops(refs["adic_caso"], lambda v: soles(v))),
        fila("Casos por mes",
             "casos del experimento cerrados, en promedio mensual",
             casos_mes_real, num(casos_mes_real, 1),
             ops(refs["casos_mes"], lambda v: num(v, 1))),
        fila("Recaudación adicional mensual",
             "suma del adicional de los casos del mes",
             adic_mes_real, miles(adic_mes_real),
             ops(refs["adic_mes"], lambda v: miles(v))),
        fila("Tasa de casos (P2P · Digital)",
             "participación de los casos sobre el total de cierres",
             tasa_real, pct(tasa_real),
             [{"id": "anual", "label": "anual 2025", "num": refs["tasa_anual"], "fmt": pct(refs["tasa_anual"])},
              {"id": "mes", "label": "prom. mensual 2025", "num": refs["tasa_prom_mensual"], "fmt": pct(refs["tasa_prom_mensual"])}]),
        fila("Ratio comisión/monto",
             "comisión / monto desembolsado, promedio de los casos",
             ratio_real, num(ratio_real, 2),
             ops(refs["ratio"], lambda v: num(v, 2))),
    ]

    return {
        "datos_hasta": fecha_subida(DATA_DIR / "Data_Seguimiento.csv"),
        "f": {
            "n_casos": f"{n_casos}",
            "n_meses": f"{meses_n}",
            "com_real": miles(com_real),
            "com_real_full": soles(com_real),
            "adicional": miles(adicional),
            "adicional_full": soles(adicional),
            "adic_caso": soles(adic_caso_real),
            "dias": num(casos["Dias de Cierre"].mean()),
            "ratio": num(ratio_real, 2),
            "cerrados_mes": f"{int(cerrados_mes + 0.5):,}",
        },
        "comp": comp,

        "evol": _bloque_evolucion(rows, "Comisión esperada", "Comisión real",
                                  en_miles=True),
    }


def build():
    proy = _proyeccion()
    seg = _seguimiento(proy.pop("_raw"))
    return {"proyeccion": proy, "seguimiento": seg}

