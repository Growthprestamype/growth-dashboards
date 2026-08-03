"""
Conexion al ORIGEN de datos: donde viven los CSV de cada proyecto.

La data ya no vive dentro del repositorio de la app. Ahora se conecta a
una ubicacion externa organizada en una carpeta por proyecto, con el
nombre del proyecto (su slug):

    <origen>/
        fast_track/
            Data_Historica.csv
            Data_Seguimiento.csv
        descuento_en_tasas/
            ...

Tres modos, elegidos con la variable DATA_ORIGEN:

  local    (por defecto) La data sigue en projects/<slug>/data/.
                         Comportamiento historico; util en desarrollo.

  carpeta  Una ruta del sistema de archivos: disco montado en Render,
           unidad de red o carpeta sincronizada (Drive/OneDrive de
           escritorio). La fecha de subida es la fecha real del archivo.
              DATA_CARPETA=/var/data/growth

  github   Un repositorio (idealmente privado) dedicado solo a la data.
           Cada archivo conserva su propia fecha de commit, que es
           exactamente "cuando lo subi". Es la via recomendada en Render:
           no requiere disco de pago y queda versionada.
              DATA_REPO=usuario/growth-data
              DATA_TOKEN=github_pat_...   (o GITHUB_TOKEN)
              DATA_RAMA=main              (opcional)
              DATA_PREFIJO=proyectos      (opcional: subcarpeta base)

Este modulo tambien sirve como almacen de los archivos de estado de la
plataforma (analitica y permisos), que se guardan bajo _plataforma/ en el
mismo origen para que sobrevivan a los reinicios de Render.
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAR_DIR = BASE_DIR / "var"          # cache y estado local (efimero)
API = "https://api.github.com"


# --- Configuracion --------------------------------------------------------


def modo() -> str:
    m = (os.environ.get("DATA_ORIGEN") or "local").strip().lower()
    if m == "carpeta" and not os.environ.get("DATA_CARPETA"):
        return "local"
    if m == "github" and not (os.environ.get("DATA_REPO") and _token()):
        return "local"
    return m if m in ("local", "carpeta", "github") else "local"


def _token() -> str:
    return (os.environ.get("DATA_TOKEN")
            or os.environ.get("GITHUB_TOKEN") or "").strip()


def _repo() -> str:
    return (os.environ.get("DATA_REPO") or "").strip()


def _rama() -> str:
    return (os.environ.get("DATA_RAMA") or "main").strip()


def _prefijo() -> str:
    return (os.environ.get("DATA_PREFIJO") or "").strip("/")


def _carpeta() -> Path:
    return Path(os.environ.get("DATA_CARPETA", "")).expanduser()


def externo() -> bool:
    """True si la data vive fuera del repositorio de la app."""
    return modo() in ("carpeta", "github")


def descripcion() -> str:
    """Texto corto para mostrar en el panel de administracion."""
    m = modo()
    if m == "carpeta":
        return f"Carpeta externa · {_carpeta()}"
    if m == "github":
        pre = f"/{_prefijo()}" if _prefijo() else ""
        return f"Repositorio · {_repo()}{pre} ({_rama()})"
    return "Local · projects/<proyecto>/data"


def _ruta(*partes: str) -> str:
    limpio = [str(p).strip("/") for p in partes if str(p).strip("/")]
    pre = _prefijo()
    if pre:
        limpio.insert(0, pre)
    return "/".join(limpio)


# --- Llamadas a GitHub ----------------------------------------------------


def _api(metodo: str, url: str, cuerpo: dict | None = None, raw: bool = False):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo, headers={
        "Authorization": "Bearer " + _token(),
        "Accept": "application/vnd.github.raw" if raw
                  else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "growth-dashboards",
    })
    with urllib.request.urlopen(req, timeout=25) as resp:
        crudo = resp.read()
        if raw:
            return crudo
        return json.loads(crudo) if crudo else {}


# --- API publica ----------------------------------------------------------


def listar(carpeta: str) -> list[dict]:
    """Archivos de una carpeta del origen.

    Devuelve [{nombre, ruta, sha, tam}]. Lista vacia si no existe.
    """
    m = modo()
    if m == "carpeta":
        base = _carpeta() / carpeta
        if not base.is_dir():
            return []
        return [
            {"nombre": p.name, "ruta": str(p), "sha": f"{p.stat().st_mtime_ns}",
             "tam": p.stat().st_size}
            for p in sorted(base.iterdir())
            if p.is_file() and not p.name.startswith(".")
        ]
    if m == "github":
        try:
            js = _api("GET", f"{API}/repos/{_repo()}/contents/"
                             f"{_ruta(carpeta)}?ref={_rama()}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise
        if not isinstance(js, list):
            return []
        return [{"nombre": it["name"], "ruta": it["path"], "sha": it["sha"],
                 "tam": it.get("size", 0)}
                for it in js if it.get("type") == "file"
                and not it["name"].startswith(".")]
    return []


def leer(ruta: str) -> bytes:
    """Contenido de un archivo del origen (ruta tal como la devolvio listar)."""
    if modo() == "carpeta":
        return Path(ruta).read_bytes()
    return _api("GET", f"{API}/repos/{_repo()}/contents/{ruta}?ref={_rama()}",
                raw=True)


def fecha(ruta: str) -> int | None:
    """Marca de tiempo (epoch) en que el archivo se subio al origen.

    En modo carpeta es la fecha de modificacion real del archivo. En modo
    github es la fecha del ultimo commit QUE TOCO ESE ARCHIVO, que es la
    unica lectura fiable: el clon superficial que hace Render comparte la
    misma marca de tiempo para todo el arbol.
    """
    m = modo()
    if m == "carpeta":
        try:
            return int(Path(ruta).stat().st_mtime)
        except OSError:
            return None
    if m == "github":
        try:
            js = _api("GET", f"{API}/repos/{_repo()}/commits"
                             f"?path={urllib.parse.quote(ruta)}"
                             f"&sha={_rama()}&per_page=1")
            if js:
                iso = js[0]["commit"]["committer"]["date"]  # 2026-07-15T12:00:00Z
                d = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
                return int(d.replace(tzinfo=datetime.timezone.utc).timestamp())
        except Exception:
            return None
    return None


# --- Estado de la plataforma (analitica y permisos) -----------------------

def _ruta_estado(nombre: str) -> str:
    return _ruta("_plataforma", nombre)


def leer_estado(nombre: str, defecto):
    """Lee un JSON de estado: primero del origen externo, luego local."""
    if modo() == "carpeta":
        p = _carpeta() / "_plataforma" / nombre
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    elif modo() == "github":
        try:
            crudo = _api("GET", f"{API}/repos/{_repo()}/contents/"
                                f"{_ruta_estado(nombre)}?ref={_rama()}", raw=True)
            return json.loads(crudo.decode("utf-8"))
        except Exception:
            pass
    local = VAR_DIR / nombre
    if local.exists():
        try:
            return json.loads(local.read_text(encoding="utf-8"))
        except Exception:
            pass
    return defecto


def guardar_estado(nombre: str, obj) -> bool:
    """Guarda un JSON de estado en local y, si hay origen externo, alli."""
    crudo = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    VAR_DIR.mkdir(exist_ok=True)
    (VAR_DIR / nombre).write_bytes(crudo)

    m = modo()
    if m == "carpeta":
        destino = _carpeta() / "_plataforma" / nombre
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(crudo)
            return True
        except OSError:
            return False
    if m == "github":
        ruta = _ruta_estado(nombre)
        cuerpo = {"message": f"plataforma: {nombre}",
                  "content": base64.b64encode(crudo).decode(),
                  "branch": _rama()}
        try:
            actual = _api("GET", f"{API}/repos/{_repo()}/contents/"
                                 f"{ruta}?ref={_rama()}")
            if isinstance(actual, dict) and actual.get("sha"):
                cuerpo["sha"] = actual["sha"]
        except Exception:
            pass
        try:
            _api("PUT", f"{API}/repos/{_repo()}/contents/{ruta}", cuerpo)
            return True
        except Exception as e:
            print("[origen] no se pudo guardar", nombre, e)
            return False
    return True


def probar() -> tuple[bool, str]:
    """Diagnostico de la conexion, para mostrarlo en el panel."""
    m = modo()
    if m == "local":
        return True, "Data local (dentro del repositorio de la app)."
    if m == "carpeta":
        base = _carpeta()
        if not base.is_dir():
            return False, f"La carpeta {base} no existe o no es accesible."
        n = len([d for d in base.iterdir() if d.is_dir()
                 and not d.name.startswith("_")])
        return True, f"Conectado · {n} carpeta(s) de proyecto en {base}."
    try:
        js = _api("GET", f"{API}/repos/{_repo()}")
        priv = "privado" if js.get("private") else "publico"
        return True, f"Conectado a {_repo()} ({priv}, rama {_rama()})."
    except urllib.error.HTTPError as e:
        return False, f"GitHub respondio {e.code}: revisa DATA_REPO y el token."
    except Exception as e:
        return False, f"No se pudo conectar: {e}"
