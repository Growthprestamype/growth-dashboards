"""
App principal. Sirve el mosaico de proyectos y, por cada proyecto, sus
vistas (proyección, seguimiento, etc.).

Las rutas son genéricas: no conocen ningún proyecto en concreto. Todo
sale del registro que arma core.registry a partir de las carpetas.

La data de cada proyecto ya no vive en este repositorio: se sincroniza
desde un origen externo (core.origen / core.datos) donde hay una carpeta
por proyecto con el nombre del proyecto. De ahí sale también la fecha
real de subida que muestran las tarjetas.
"""

import os

from flask import (Flask, abort, redirect, render_template, request, session,
                   url_for)
from jinja2 import ChoiceLoader, FileSystemLoader

from core import analitica, datos, panel
from core.admin import init_admin
from core.auth import init_auth
from core.fechas import fecha_subida_dir
from core.registry import (
    BASE_DIR,
    PROJECTS_DIR,
    STATIC_DIR,
    TEMPLATES_DIR,
    discover_projects,
)

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    template_folder=str(TEMPLATES_DIR),
)

# El loader busca primero en /templates (base, índice) y luego dentro de
# /projects, lo que permite referenciar las vistas como
# "<carpeta>/templates/<vista>.html".
app.jinja_loader = ChoiceLoader(
    [
        FileSystemLoader(str(TEMPLATES_DIR)),
        FileSystemLoader(str(PROJECTS_DIR)),
    ]
)

# Protege toda la plataforma detrás de un inicio de sesión.
init_auth(app)

# --- Registro y caché --------------------------------------------------

_REGISTRY = {}
_DATA_CACHE = {}


def get_registry():
    global _REGISTRY
    if not _REGISTRY:
        _REGISTRY = discover_projects()
    return _REGISTRY


def invalidar_cache(slug=None):
    """Olvida los resultados calculados para que se recalculen con la
    data recién sincronizada."""
    if slug:
        _DATA_CACHE.pop(slug, None)
    else:
        _DATA_CACHE.clear()


def get_project_data(project, refresh=False):
    # Trae la data del origen externo si toca (TTL interno de core.datos).
    datos.asegurar(project.slug, project.path / "data")
    if refresh or project.slug not in _DATA_CACHE:
        _DATA_CACHE[project.slug] = project.build()
    return _DATA_CACHE[project.slug]


def es_admin() -> bool:
    return panel.es_admin(session.get("email"))


@app.context_processor
def _inyectar():
    return {"es_admin": es_admin()}


# El panel de administración necesita el registro y poder limpiar la caché.
init_admin(app, get_registry, invalidar_cache)


# --- Rutas -------------------------------------------------------------


@app.route("/salud")
def salud():
    return {"ok": True}


@app.route("/")
def index():
    admin = es_admin()
    visibles = [p for p in get_registry().values()
                if panel.activo(p.slug) or admin]
    projects = sorted(visibles,
                      key=lambda p: (panel.orden(p.slug, p.order), p.title))

    kpis = []
    tags_path = BASE_DIR / "tags.json"
    if tags_path.exists():
        import json
        kpis = json.loads(tags_path.read_text(encoding="utf-8")).get("kpis", [])

    # La data se sincroniza de forma perezosa para no frenar el arranque.
    for p in projects:
        datos.asegurar(p.slug, p.path / "data")

    fechas = {p.slug: fecha_subida_dir(p.path / "data") for p in projects}
    ocultos = {p.slug for p in projects if not panel.activo(p.slug)}
    return render_template("index.html", projects=projects, kpis=kpis,
                           fechas=fechas, ocultos=ocultos)


@app.route("/p/<slug>")
def project_home(slug):
    project = get_registry().get(slug)
    if not project or not project.views:
        abort(404)
    return redirect(url_for("project_view", slug=slug,
                            view=project.views[0]["slug"]))


@app.route("/p/<slug>/<view>")
def project_view(slug, view):
    project = get_registry().get(slug)
    if not project or view not in project.view_slugs:
        abort(404)
    if not panel.activo(slug) and not es_admin():
        abort(404)

    refresh = request.args.get("refresh") == "1"
    data = get_project_data(project, refresh=refresh)
    context = data.get(view, {})

    analitica.registrar("vista", correo=session.get("email"),
                        slug=slug, vista=view)

    # notas contextuales/metodológicas opcionales del proyecto
    notas_tpl = None
    if (project.path / "templates" / "_notas.html").exists():
        notas_tpl = f"{project.dirname}/templates/_notas.html"

    return render_template(
        project.template_for(view),
        project=project,
        views=project.views,
        current_view=view,
        notas_tpl=notas_tpl,
        oculto=not panel.activo(slug),
        **context,
    )


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


if __name__ == "__main__":
    # Local: python app.py  ->  http://127.0.0.1:5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
