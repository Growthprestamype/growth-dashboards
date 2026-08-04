"""
Graficos SVG generados en el servidor. Sin librerias de cliente.

  - bar_chart     : barras verticales con eje Y (escala), eje X (meses),
                    caption opcional bajo cada barra y tooltip reactivo.
  - line_chart    : linea de tendencia con eje Y (escala), eje X (meses) y
                    puntos que aparecen con tooltip al pasar el mouse.
  - increment_bars: comparacion Historico vs Potencial resaltando el
                    incremento (cap de color acento sobre el potencial).

Los colores salen de variables CSS del sitio; la interactividad la maneja
static/js/charts.js leyendo el atributo data-tip.
"""

from __future__ import annotations

import math
from html import escape

W = 760
PAD_L = 52   # espacio para etiquetas del eje Y
PAD_R = 14
PAD_T = 18
NICE = (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10)


def _nice_ceil(x):
    if x <= 0:
        return 1.0
    exp = math.floor(math.log10(x))
    base = 10 ** exp
    f = x / base
    for m in NICE:
        if f <= m + 1e-9:
            return m * base
    return 10 * base


def _ticks(vmax, n=4):
    top = _nice_ceil(vmax)
    return [top * i / n for i in range(n + 1)], top


def _grid_and_yaxis(parts, top, ticks, plot_top, plot_bot, y_fmt,
                    w=W, pad_l=PAD_L, pad_r=PAD_R):
    span = plot_bot - plot_top
    for t in ticks:
        y = plot_bot - (t / top) * span if top else plot_bot
        parts.append(
            f'<line class="grid" x1="{pad_l}" y1="{y:.1f}" '
            f'x2="{w - pad_r}" y2="{y:.1f}"/>'
        )
        parts.append(
            f'<text class="axis-lab" x="{pad_l - 8}" y="{y + 4:.1f}" '
            f'text-anchor="end">{escape(y_fmt(t))}</text>'
        )


# --- Capas opcionales (negocio general, ticket promedio, linea base) ------
#
# Las capas se dibujan dentro de <g data-capa="..."> con su etiqueta en
# data-nombre, para que static/js/capas.js arme la "tuerca" y las pueda
# encender o apagar sin recargar. Cada capa con unidades propias trae su
# PROPIA escala, siempre a la DERECHA, para no cruzarse con la del eje
# izquierdo (que manda sobre las barras principales).

ANCHO_EJE_DER = 54      # espacio reservado por cada eje derecho


def _fmt_casos(v):
    return f"{v:,.0f}".replace(",", " ")


def _fmt_miles_soles(v):
    if abs(v) >= 1e6:
        return f"S/{v / 1e6:.1f}M"
    if abs(v) >= 1000:
        return f"S/{v / 1000:,.0f}k"
    return f"S/{v:,.0f}"


def _capas_activas(capas):
    """[(clave, capa)] de las capas con eje propio, en orden de dibujo."""
    if not capas:
        return []
    return [(k, capas[k]) for k in ("fondo", "marca")
            if capas.get(k) and any(v is not None
                                    for v in capas[k].get("valores", []))]


def _reservar_derecha(capas):
    return ANCHO_EJE_DER * len(_capas_activas(capas))


def _eje_derecho(parts, capa, indice, top_v, ticks, plot_top, plot_bot,
                 plot_right, fmt):
    """Etiquetas del eje derecho, alineadas a la grilla del eje izquierdo."""
    x = plot_right + 12 + indice * ANCHO_EJE_DER
    span = plot_bot - plot_top
    if indice == 0:
        parts.append(f'<line class="eje-sep" x1="{plot_right + 4}" '
                     f'y1="{plot_top - 2}" x2="{plot_right + 4}" '
                     f'y2="{plot_bot}"/>')
    for t in ticks:
        frac = (t / ticks[-1]) if ticks[-1] else 0
        y = plot_bot - frac * span
        parts.append(
            f'<text class="axis-lab der" x="{x}" y="{y + 4:.1f}">'
            f'{escape(fmt(frac * top_v))}</text>'
        )
    parts.append(
        f'<text class="axis-tit der" x="{x}" y="{plot_top - 7:.1f}">'
        f'{escape(capa.get("unidad", ""))}</text>'
    )


def _dibujar_fondo(parts, capa, xs, slot, top_v, plot_top, plot_bot,
                   plot_right, ticks, indice):
    """Barras tenues del negocio general, detras de la serie principal."""
    span = plot_bot - plot_top
    ancho = min(slot * 0.66, 74)
    parts.append(f'<g data-capa="fondo" data-nombre="{escape(capa["nombre"])}">')
    for i, cx in enumerate(xs):
        v = capa["valores"][i]
        if v is None:
            continue
        h = (v / top_v) * span if top_v else 0
        x0 = cx - ancho / 2
        parts.append(
            f'<rect class="bar-fondo" x="{x0:.1f}" '
            f'y="{plot_bot - h:.1f}" width="{ancho:.1f}" height="{h:.1f}" '
            f'data-tip="{escape(capa["nombre"])} · {_fmt_casos(v)} casos"/>'
        )
        parts.append(
            f'<line class="bar-fondo-tope" x1="{x0:.1f}" '
            f'y1="{plot_bot - h:.1f}" x2="{x0 + ancho:.1f}" '
            f'y2="{plot_bot - h:.1f}"/>'
        )
    _eje_derecho(parts, capa, indice, top_v, ticks, plot_top, plot_bot,
                 plot_right, _fmt_casos)
    parts.append("</g>")


def _dibujar_marca(parts, capa, xs, top_v, plot_top, plot_bot, plot_right,
                   ticks, indice):
    """Ticket promedio del mes como marca sobre las barras."""
    span = plot_bot - plot_top
    pts = []
    for i, cx in enumerate(xs):
        v = capa["valores"][i]
        if v is None:
            continue
        y = plot_bot - (v / top_v) * span if top_v else plot_bot
        pts.append((cx, y, v))
    parts.append(f'<g data-capa="marca" data-nombre="{escape(capa["nombre"])}">')
    if len(pts) > 1:
        parts.append('<polyline class="marca-ln" points="'
                     + " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts) + '"/>')
    for x, y, v in pts:
        parts.append(
            f'<g class="marca-pt" data-tip="{escape(capa["nombre"])} · '
            f'{_fmt_miles_soles(v)}">'
            f'<line x1="{x - 11:.1f}" y1="{y:.1f}" x2="{x + 11:.1f}" '
            f'y2="{y:.1f}"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4"/></g>'
        )
    _eje_derecho(parts, capa, indice, top_v, ticks, plot_top, plot_bot,
                 plot_right, _fmt_miles_soles)
    parts.append("</g>")


def _dibujar_base(parts, valores, nombre, top, plot_top, plot_bot,
                  plot_left, plot_right, fmt):
    """Linea base: promedio del periodo de la serie principal."""
    vals = [v for v in valores if v is not None]
    if len(vals) < 2:
        return
    prom = sum(vals) / len(vals)
    span = plot_bot - plot_top
    y = plot_bot - (prom / top) * span if top else plot_bot
    etiqueta = f"promedio {fmt(prom)}"
    ancho_lab = len(etiqueta) * 6.4 + 14
    # La etiqueta se coloca del lado donde las barras son más bajas, para
    # que nunca tape la serie principal.
    tercio = max(1, len(vals) // 3)
    izq = max(vals[:tercio], default=0)
    der = max(vals[-tercio:], default=0)
    x_lab = (plot_left + 6 if izq <= der
             else plot_right - ancho_lab - 2)
    parts.append(f'<g data-capa="base" data-nombre="{escape(nombre)}">')
    parts.append(
        f'<line class="base-line" x1="{plot_left}" y1="{y:.1f}" '
        f'x2="{plot_right}" y2="{y:.1f}"/>'
    )
    parts.append(
        f'<rect class="base-caja" x="{x_lab:.1f}" y="{y - 17:.1f}" '
        f'width="{ancho_lab:.0f}" height="15" rx="2"/>'
    )
    parts.append(
        f'<text class="base-lab" x="{x_lab + 7:.1f}" y="{y - 6:.1f}">'
        f'{escape(etiqueta)}</text>'
    )
    parts.append("</g>")


def bar_chart(points, *, y_fmt, tip_fmt=None, height=250,
              capas=None):
    if not points:
        return ""
    tip_fmt = tip_fmt or y_fmt
    H = height
    pad_bot = 46
    plot_top, plot_bot = PAD_T, H - pad_bot
    span = plot_bot - plot_top
    n = len(points)
    reserva = _reservar_derecha(capas)
    plot_right = W - PAD_R - reserva
    slot = (plot_right - PAD_L) / n
    bar_w = min(slot * 0.5, 56)

    vals = [max(0.0, float(p["value"])) for p in points]
    ticks, top = _ticks(max(vals) or 1)
    xs = [PAD_L + i * slot + slot / 2 for i in range(n)]

    parts = [f'<svg class="svg-chart" viewBox="0 0 {W} {H}" width="100%" '
             f'preserveAspectRatio="xMidYMid meet" role="img">']
    _grid_and_yaxis(parts, top, ticks, plot_top, plot_bot, y_fmt,
                    pad_r=W - plot_right)

    for idx, (clave, capa) in enumerate(_capas_activas(capas)):
        limpio = [v for v in capa["valores"] if v is not None]
        _, top_v = _ticks(max(limpio) or 1)
        if clave == "fondo":
            _dibujar_fondo(parts, capa, xs, slot, top_v, plot_top, plot_bot,
                           plot_right, ticks, idx)

    for i, p in enumerate(points):
        v = vals[i]
        bh = (v / top) * span if top else 0
        cx = xs[i]
        x = cx - bar_w / 2
        y = plot_bot - bh
        tip = f'{p["label"]} · {tip_fmt(v)}'
        parts.append(
            f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{bh:.1f}" rx="4" data-tip="{escape(tip)}" '
            f'style="animation-delay:{i * 0.05:.2f}s"/>'
        )
        parts.append(
            f'<text class="x-lab" x="{cx:.1f}" y="{H - 26:.1f}" '
            f'text-anchor="middle">{escape(str(p["label"]))}</text>'
        )
        if p.get("caption"):
            parts.append(
                f'<text class="x-cap" x="{cx:.1f}" y="{H - 11:.1f}" '
                f'text-anchor="middle">{escape(str(p["caption"]))}</text>'
            )

    if capas and capas.get("base"):
        _dibujar_base(parts, vals, capas["base"]["nombre"], top, plot_top,
                      plot_bot, PAD_L, plot_right, tip_fmt)
    for idx, (clave, capa) in enumerate(_capas_activas(capas)):
        if clave == "marca":
            limpio = [v for v in capa["valores"] if v is not None]
            _, top_v = _ticks(max(limpio) or 1)
            _dibujar_marca(parts, capa, xs, top_v, plot_top, plot_bot,
                           plot_right, ticks, idx)

    parts.append("</svg>")
    return "".join(parts)


def line_chart(labels, values, *, y_fmt, tip_fmt=None, height=150):
    """Linea compacta para small-multiples. Usa un viewBox angosto (~360)
    para que el texto de los ejes sea legible casi a escala 1:1."""
    pts = [(labels[i], float(v)) for i, v in enumerate(values) if v is not None]
    if len(pts) < 2:
        return ""
    tip_fmt = tip_fmt or y_fmt

    w, pad_l, pad_r = 360, 40, 12
    H = height
    pad_bot = 28
    plot_top, plot_bot = 14, H - pad_bot
    span = plot_bot - plot_top
    vals = [v for _, v in pts]
    ticks, top = _ticks(max(vals) or 1, n=3)

    n = len(pts)
    plot_w = w - pad_l - pad_r
    every = 1 if n <= 8 else 2

    def xy(i, v):
        x = pad_l + (i * plot_w / (n - 1))
        y = plot_bot - (v / top) * span if top else plot_bot
        return x, y

    coords = [xy(i, v) for i, (_, v) in enumerate(pts)]

    parts = [f'<svg class="svg-chart" viewBox="0 0 {w} {H}" width="100%" '
             f'preserveAspectRatio="xMidYMid meet" role="img">']
    _grid_and_yaxis(parts, top, ticks, plot_top, plot_bot, y_fmt,
                    w=w, pad_l=pad_l, pad_r=pad_r)

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    parts.append(f'<polyline class="ln-line" points="{line}"/>')

    for i, (lab, v) in enumerate(pts):
        x, y = coords[i]
        tip = f'{lab} · {tip_fmt(v)}'
        parts.append(
            f'<g class="ln-pt" data-tip="{escape(tip)}">'
            f'<circle class="hit" cx="{x:.1f}" cy="{y:.1f}" r="14"/>'
            f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="4"/></g>'
        )
        if i % every == 0 or i == n - 1:
            parts.append(
                f'<text class="x-lab sm" x="{x:.1f}" y="{H - 9:.1f}" '
                f'text-anchor="middle">{escape(str(lab))}</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


def increment_bars(hist, pot, *, fmt, height=230,
                   label_a="Histórico", label_b="Potencial",
                   label_inc="Adicional"):
    """Comparacion A vs B. La barra B lleva un cap de color acento igual al
    incremento, para que la diferencia se note pese a ser pequena."""
    H = height
    pad_bot = 34
    plot_top, plot_bot = PAD_T, H - pad_bot
    span = plot_bot - plot_top
    ticks, top = _ticks(max(hist, pot) or 1)

    cats = [(label_a, hist, False), (label_b, pot, True)]
    n = len(cats)
    slot = (W - PAD_L - PAD_R) / n
    bar_w = min(slot * 0.32, 120)

    parts = [f'<svg class="svg-chart" viewBox="0 0 {W} {H}" width="100%" '
             f'preserveAspectRatio="xMidYMid meet" role="img">']
    _grid_and_yaxis(parts, top, ticks,
                    plot_top, plot_bot, lambda v: f"{v/1e6:.1f}M")

    for i, (lab, val, split) in enumerate(cats):
        cx = PAD_L + i * slot + slot / 2
        x = cx - bar_w / 2
        if not split:
            bh = (val / top) * span
            parts.append(
                f'<rect class="bar" x="{x:.1f}" y="{plot_bot - bh:.1f}" '
                f'width="{bar_w:.1f}" height="{bh:.1f}" rx="4" '
                f'data-tip="{escape(lab + " · " + fmt(val))}"/>'
            )
        else:
            base_h = (hist / top) * span
            inc_h = ((pot - hist) / top) * span
            y_base = plot_bot - base_h
            y_inc = y_base - inc_h
            parts.append(
                f'<rect class="bar" x="{x:.1f}" y="{y_base:.1f}" '
                f'width="{bar_w:.1f}" height="{base_h:.1f}" rx="0" '
                f'data-tip="{escape(label_a + " · " + fmt(hist))}"/>'
            )
            parts.append(
                f'<rect class="bar cap" x="{x:.1f}" y="{y_inc:.1f}" '
                f'width="{bar_w:.1f}" height="{max(inc_h,3):.1f}" rx="4" '
                f'data-tip="{escape(label_inc + " · " + fmt(pot - hist))}"/>'
            )
            # guia punteada que marca el nivel del historico
            parts.append(
                f'<line class="lead" x1="{PAD_L}" y1="{y_base:.1f}" '
                f'x2="{x + bar_w:.1f}" y2="{y_base:.1f}"/>'
            )
        parts.append(
            f'<text class="x-lab" x="{cx:.1f}" y="{H - 12:.1f}" '
            f'text-anchor="middle">{escape(lab)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def dual_bar_chart(points, *, y_fmt, tip_fmt=None,
                   name_a="Serie A", name_b="Serie B", height=260,
                   capas=None):
    """Barras agrupadas (dos series por periodo). La serie A usa tinta
    (referencia) y la B el color acento (propuesta/real destacado).

    points: [{"label": str, "a": float, "b": float, "caption": str?}]
    """
    if not points:
        return ""
    tip_fmt = tip_fmt or y_fmt
    H = height
    pad_bot = 46
    plot_top, plot_bot = PAD_T + 14, H - pad_bot  # deja sitio a la leyenda
    span = plot_bot - plot_top
    n = len(points)
    reserva = _reservar_derecha(capas)
    plot_right = W - PAD_R - reserva
    slot = (plot_right - PAD_L) / n
    bar_w = min(slot * 0.26, 30)
    gap = min(6, bar_w * 0.3)

    vals = []
    for p in points:
        vals.append(max(0.0, float(p.get("a") or 0)))
        vals.append(max(0.0, float(p.get("b") or 0)))
    ticks, top = _ticks(max(vals) or 1)
    xs = [PAD_L + i * slot + slot / 2 for i in range(n)]

    parts = [f'<svg class="svg-chart" viewBox="0 0 {W} {H}" width="100%" '
             f'preserveAspectRatio="xMidYMid meet" role="img">']
    _grid_and_yaxis(parts, top, ticks, plot_top, plot_bot, y_fmt,
                    pad_r=W - plot_right)

    for idx, (clave, capa) in enumerate(_capas_activas(capas)):
        limpio = [v for v in capa["valores"] if v is not None]
        _, top_v = _ticks(max(limpio) or 1)
        if clave == "fondo":
            _dibujar_fondo(parts, capa, xs, slot, top_v, plot_top, plot_bot,
                           plot_right, ticks, idx)

    # leyenda, de izquierda a derecha desde el borde del área de trazado
    lx = PAD_L
    for nombre, cls in ((name_a, "a"), (name_b, "b")):
        parts.append(
            f'<g class="legend">'
            f'<rect class="lg-sw {cls}" x="{lx}" y="4" width="11" height="11" '
            f'rx="2"/>'
            f'<text class="lg-lab" x="{lx + 17}" y="14">{escape(nombre)}</text>'
            f'</g>'
        )
        lx += 17 + len(nombre) * 6.6 + 22

    for i, p in enumerate(points):
        cx = xs[i]
        va = max(0.0, float(p.get("a") or 0))
        vb = max(0.0, float(p.get("b") or 0))
        for j, (v, cls, nm) in enumerate(
            [(va, "a", name_a), (vb, "b", name_b)]
        ):
            bh = (v / top) * span if top else 0
            x = cx - (bar_w + gap / 2) + j * (bar_w + gap)
            y = plot_bot - bh
            tip = f'{p["label"]} · {nm} · {tip_fmt(v)}'
            parts.append(
                f'<rect class="bar {cls}" x="{x:.1f}" y="{y:.1f}" '
                f'width="{bar_w:.1f}" height="{bh:.1f}" rx="3" '
                f'data-tip="{escape(tip)}" '
                f'style="animation-delay:{i * 0.05:.2f}s"/>'
            )
        parts.append(
            f'<text class="x-lab" x="{cx:.1f}" y="{H - 26:.1f}" '
            f'text-anchor="middle">{escape(str(p["label"]))}</text>'
        )
        if p.get("caption"):
            parts.append(
                f'<text class="x-cap" x="{cx:.1f}" y="{H - 11:.1f}" '
                f'text-anchor="middle">{escape(str(p["caption"]))}</text>'
            )

    if capas and capas.get("base"):
        principal = [max(0.0, float(p.get("b") or 0)) for p in points]
        _dibujar_base(parts, principal, capas["base"]["nombre"], top,
                      plot_top, plot_bot, PAD_L, plot_right, tip_fmt)
    for idx, (clave, capa) in enumerate(_capas_activas(capas)):
        if clave == "marca":
            limpio = [v for v in capa["valores"] if v is not None]
            _, top_v = _ticks(max(limpio) or 1)
            _dibujar_marca(parts, capa, xs, top_v, plot_top, plot_bot,
                           plot_right, ticks, idx)

    parts.append("</svg>")
    return "".join(parts)
