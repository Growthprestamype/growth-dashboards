"""
Fecha de subida de un archivo de datos.

Orden de resolucion (de mas fiable a menos):

  1. _fechas.json  El sidecar que deja core.datos al sincronizar con el
                   origen externo. Guarda, por archivo, la fecha real en
                   que se subio. Es la fuente correcta.

  2. git log       Solo si el repositorio tiene historia completa (en
                   desarrollo). Render clona con --depth 1: con un unico
                   commit, git devuelve la MISMA marca de tiempo para
                   todos los archivos, asi que ahi se descarta.

  3. mtime         Ultimo recurso. En local es la fecha real de copia;
                   despues de un deploy equivale a la fecha del deploy.

La API publica no cambio: los procesadores siguen llamando
fecha_subida(ruta) y fecha_subida_dir(carpeta).
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
from pathlib import Path

_MESES_MIN = ["ene", "feb", "mar", "abr", "may", "jun",
              "jul", "ago", "sep", "oct", "nov", "dic"]

SIDECAR = "_fechas.json"


def _fmt(ts: float) -> str:
    d = datetime.datetime.fromtimestamp(ts)
    return f"{d.day} {_MESES_MIN[d.month - 1]} {d.year}"


def formatear(ts: float | None) -> str | None:
    return _fmt(ts) if ts else None


# --- Fuentes --------------------------------------------------------------


def _del_sidecar(path: Path) -> int | None:
    archivo = path.parent / SIDECAR
    if not archivo.exists():
        return None
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except Exception:
        return None
    ts = datos.get(path.name)
    return int(ts) if ts else None


def _repo_superficial(cwd: Path) -> bool:
    """True si el clon es --depth 1 (git no distingue fechas por archivo)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            capture_output=True, text=True, timeout=5, cwd=str(cwd),
        )
        if out.returncode == 0:
            return out.stdout.strip() == "true"
    except Exception:
        pass
    return False


def _de_git(path: Path) -> int | None:
    try:
        if _repo_superficial(path.parent):
            return None
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", path.name],
            capture_output=True, text=True, timeout=5, cwd=str(path.parent),
        )
        crudo = out.stdout.strip()
        if out.returncode == 0 and crudo:
            return int(crudo)
    except Exception:
        pass
    return None


# --- API publica ----------------------------------------------------------


def ts_subida(path) -> int | None:
    """Marca de tiempo (epoch) en que se subio/actualizo el archivo."""
    path = Path(path)
    if not path.exists():
        return None
    for fuente in (_del_sidecar, _de_git):
        ts = fuente(path)
        if ts:
            return ts
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return None


def fecha_subida(path) -> str | None:
    """Fecha (es-PE corta) en que se subio/actualizo el archivo."""
    return formatear(ts_subida(path))


def _archivos(dirpath: Path) -> list[Path]:
    return sorted(p for p in dirpath.glob("*.csv") if not p.name.startswith("_"))


def ts_subida_dir(dirpath) -> int | None:
    """Fecha (epoch) mas reciente entre los archivos de datos del proyecto.

    Se toma el maximo real por archivo: si solo se actualizo el CSV de
    seguimiento, la tarjeta muestra esa fecha y no la de un deploy.
    """
    dirpath = Path(dirpath)
    if not dirpath.is_dir():
        return None
    fechas = [ts for ts in (ts_subida(a) for a in _archivos(dirpath)) if ts]
    return max(fechas) if fechas else None


def fecha_subida_dir(dirpath) -> str | None:
    return formatear(ts_subida_dir(dirpath))


def detalle_dir(dirpath) -> list[dict]:
    """[{nombre, ts, fecha}] por archivo. Para el panel de administracion."""
    dirpath = Path(dirpath)
    if not dirpath.is_dir():
        return []
    salida = []
    for a in _archivos(dirpath):
        ts = ts_subida(a)
        salida.append({"nombre": a.name, "ts": ts, "fecha": formatear(ts),
                       "tam": a.stat().st_size})
    return sorted(salida, key=lambda x: -(x["ts"] or 0))
