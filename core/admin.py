"""
Panel de administracion: quien entra, que se ve, que esta publicado.

Acceso restringido a los correos de la variable de entorno ADMIN_EMAILS.
Quien no este en esa lista ni siquiera ve el enlace en la cabecera.

Responde a cuatro preguntas:
  1. Quienes entran y con que frecuencia.
  2. Que dashboards se ven mas (y cuales nadie abre).
  3. Que esta activo, que esta oculto y con que prioridad se muestra.
  4. Que tan fresca esta la data de cada proyecto.
"""

from __future__ import annotations

import time
from html import escape

from flask import (Blueprint, redirect, render_template, request, session,
                   url_for)

from core import analitica, datos, fechas, origen, panel

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Umbrales de frescura de la data (dias)
FRESCO_DIAS = 10
POR_VENCER_DIAS = 30

_get_registry = None
_invalidar = None


def _correo() -> str:
    return (session.get("email") or "").lower()


def _clasificar(ts: int | None) -> tuple[str, str]:
    """(clave, etiqueta) del estado de frescura de la data."""
    if not ts:
        return "sin-datos", "sin datos"
    dias = (int(time.time()) - ts) // 86400
    if dias <= FRESCO_DIAS:
        return "fresco", f"al día · {dias} d"
    if dias <= POR_VENCER_DIAS:
        return "por-vencer", f"por vencer · {dias} d"
    return "vencido", f"desactualizado · {dias} d"


def _grafico(serie: list[dict]) -> str:
    """Barras diarias de vistas con marca de accesos. SVG, sin librerias."""
    if not serie:
        return ""
    w, h = 980, 132
    pad_b, pad_t = 22, 12
    n = len(serie)
    hueco = w / n
    ancho = min(hueco * 0.55, 20)
    tope = max([d["vistas"] for d in serie] + [1])
    partes = [f'<svg class="adm-graf" viewBox="0 0 {w} {h}" width="100%" '
              f'preserveAspectRatio="none" role="img" '
              f'aria-label="Actividad diaria">']
    for i, d in enumerate(serie):
        alto = (d["vistas"] / tope) * (h - pad_b - pad_t)
        x = i * hueco + (hueco - ancho) / 2
        y = h - pad_b - alto
        tip = f'{d["etiqueta"]} · {d["vistas"]} vistas · {d["accesos"]} accesos'
        partes.append(f'<rect class="adm-barra" x="{x:.1f}" y="{y:.1f}" '
                      f'width="{ancho:.1f}" height="{max(alto, 1):.1f}" '
                      f'data-tip="{escape(tip)}"/>')
        if d["accesos"]:
            partes.append(f'<circle class="adm-punto" cx="{x + ancho / 2:.1f}" '
                          f'cy="{max(y - 6, 5):.1f}" r="3" '
                          f'data-tip="{escape(tip)}"/>')
        if n <= 16 or i % max(1, n // 10) == 0 or i == n - 1:
            partes.append(f'<text class="adm-eje" x="{x + ancho / 2:.1f}" '
                          f'y="{h - 7}" text-anchor="middle">'
                          f'{d["etiqueta"]}</text>')
    partes.append("</svg>")
    return "".join(partes)


def _proyectos_admin(dias: int):
    """Cruza registro de proyectos + analitica + frescura de la data."""
    registro = _get_registry()
    res = analitica.resumen(dias)
    filas = []
    for p in registro.values():
        uso = res["tablero"].get(p.slug, {})
        ts = fechas.ts_subida_dir(p.path / "data")
        clave, etiqueta = _clasificar(ts)
        filas.append({
            "slug": p.slug,
            "titulo": p.title,
            "tags": p.tags,
            "activo": panel.activo(p.slug),
            "orden": panel.orden(p.slug, p.order),
            "vistas": uso.get("vistas", 0),
            "vistas_periodo": uso.get("vistas_periodo", 0),
            "vistas_7": uso.get("vistas_7", 0),
            "personas": uso.get("personas_unicas", 0),
            "ultima": uso.get("ultima_humano", "nunca"),
            "fecha_datos": fechas.formatear(ts) or "—",
            "frescura": clave,
            "frescura_txt": etiqueta,
            "archivos": fechas.detalle_dir(p.path / "data"),
            "sync": datos.estado_por_proyecto(p.slug),
        })
    filas.sort(key=lambda f: (f["orden"], f["titulo"]))
    return filas, res


def _titulo(filas, slug):
    for f in filas:
        if f["slug"] == slug:
            return f["titulo"]
    return slug


@admin_bp.before_request
def _solo_admins():
    if not panel.es_admin(_correo()):
        return render_template("403.html"), 403
    return None


@admin_bp.route("/")
def inicio():
    dias = 7 if request.args.get("rango") == "7" else 30
    filas, res = _proyectos_admin(dias)
    ok_origen, detalle_origen = origen.probar()
    vistos = sum(1 for f in filas if f["vistas"])
    return render_template(
        "admin.html",
        dias=dias,
        resumen=res,
        grafico=_grafico(res["serie"]),
        proyectos=filas,
        titulos={f["slug"]: f["titulo"] for f in filas},
        top_titulo=_titulo(filas, res["top"]["slug"]) if res["top"] else None,
        sin_visitas=len(filas) - vistos,
        accesos=panel.lista_accesos(),
        registro=panel.registro_accesos(),
        admins=sorted(panel.admins()),
        origen_desc=origen.descripcion(),
        origen_ok=ok_origen,
        origen_detalle=detalle_origen,
        origen_externo=origen.externo(),
        mensaje=request.args.get("m"),
        error=request.args.get("e"),
    )


@admin_bp.route("/accion", methods=["POST"])
def accion():
    quien = _correo()
    que = request.form.get("accion", "")
    slug = (request.form.get("slug") or "").strip()
    correo = (request.form.get("correo") or "").strip().lower()
    rango = request.form.get("rango", "30")
    mensaje = error = None

    if que in ("activar", "ocultar"):
        mensaje = panel.fijar_activo(slug, que == "activar", quien)
    elif que in ("subir", "bajar"):
        filas, _ = _proyectos_admin(30)
        mensaje = panel.mover(slug, -1 if que == "subir" else 1,
                              [f["slug"] for f in filas], quien)
    elif que in ("agregar", "bloquear", "restaurar", "quitar"):
        fn = {"agregar": panel.agregar_correo,
              "bloquear": panel.bloquear_correo,
              "restaurar": panel.restaurar_correo,
              "quitar": panel.quitar_correo}[que]
        ok, msg = fn(correo, quien)
        mensaje, error = (msg, None) if ok else (None, msg)
    elif que == "sincronizar":
        registro = _get_registry()
        objetivo = ([registro[slug]] if slug in registro
                    else list(registro.values()))
        informe = datos.sincronizar_todos(objetivo, forzar=True)
        bajados = sum(i["descargados"] for i in informe.values())
        fallos = [s for s, i in informe.items() if not i["ok"]]
        if _invalidar:
            _invalidar()
        if not origen.externo():
            error = ("No hay origen externo configurado (DATA_ORIGEN): "
                     "la data se lee del propio repositorio.")
        elif fallos:
            error = (f"Sincronizado con avisos · {bajados} archivo(s). "
                     f"Revisar: {', '.join(fallos)}")
        else:
            mensaje = (f"Datos sincronizados · {bajados} archivo(s) "
                       f"actualizado(s) desde el origen.")
    elif que == "guardar_analitica":
        mensaje = ("Analítica guardada en el origen."
                   if analitica.guardar(forzar=True)
                   else "No se pudo guardar en el origen; queda en local.")
    else:
        error = "Acción no reconocida."

    return redirect(url_for("admin.inicio", rango=rango, m=mensaje, e=error))


def init_admin(app, get_registry, invalidar_cache=None):
    global _get_registry, _invalidar
    _get_registry = get_registry
    _invalidar = invalidar_cache
    app.register_blueprint(admin_bp)
