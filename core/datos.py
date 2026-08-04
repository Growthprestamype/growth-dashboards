"""
Sincronizacion de la data de cada proyecto desde el origen externo.

Trae los archivos de <origen>/<slug>/ a projects/<slug>/data/ y deja
junto a ellos un archivo _fechas.json con la FECHA REAL DE SUBIDA de cada
archivo (la del origen, no la del deploy). Los procesadores de cada
proyecto no cambian: siguen leyendo su carpeta data/ y llamando a
core.fechas.fecha_subida(), que ahora consulta ese _fechas.json.

Por que hacia falta: Render clona el repositorio en modo superficial
(--depth 1). Con un solo commit en la historia, `git log` devuelve la
misma marca de tiempo para todos los archivos, y la fecha de modificacion
en disco es la del checkout. Resultado: al actualizar un solo CSV, todas
las tarjetas mostraban la misma fecha nueva. Con el origen externo cada
archivo conserva su propia fecha.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from core import origen

SIDECAR = "_fechas.json"
_TTL_SEG = 15 * 60          # revalida como maximo cada 15 minutos
_ultima_sync: dict[str, float] = {}


def _estado_path(slug: str) -> Path:
    origen.VAR_DIR.mkdir(exist_ok=True)
    return origen.VAR_DIR / f"sync_{slug}.json"


def _leer_json(path: Path, defecto):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return defecto


def sincronizar(slug: str, destino: Path, forzar: bool = False) -> dict:
    """Baja la data del proyecto y actualiza las fechas reales.

    Devuelve {ok, modo, descargados, sin_cambios, archivos, error}.
    """
    resultado = {"ok": True, "modo": origen.modo(), "descargados": 0,
                 "sin_cambios": 0, "archivos": [], "error": None}

    if not origen.externo():
        # Modo local: nada que traer; las fechas salen de git/mtime.
        return resultado

    try:
        remotos = origen.listar(slug)
    except Exception as e:
        resultado.update(ok=False, error=f"No se pudo listar {slug}: {e}")
        return resultado

    if not remotos:
        resultado.update(
            ok=False,
            error=f"No hay carpeta «{slug}» en el origen (o está vacía).")
        return resultado

    destino.mkdir(parents=True, exist_ok=True)
    estado = _leer_json(_estado_path(slug), {})
    nuevo_estado: dict[str, dict] = {}
    fechas: dict[str, int] = {}

    for item in remotos:
        nombre = item["nombre"]
        if not nombre.lower().endswith((".csv", ".xls", ".xlsx", ".json")):
            continue
        previo = estado.get(nombre) or {}
        archivo_local = destino / nombre
        cambio = (forzar or previo.get("sha") != item["sha"]
                  or not archivo_local.exists())

        if cambio:
            try:
                archivo_local.write_bytes(origen.leer(item["ruta"]))
                resultado["descargados"] += 1
            except Exception as e:
                resultado.update(ok=False,
                                 error=f"Fallo al bajar {nombre}: {e}")
                continue
            ts = (item.get("ts") or origen.fecha(item["ruta"])
                  or int(time.time()))
        else:
            resultado["sin_cambios"] += 1
            ts = (previo.get("ts") or item.get("ts")
                  or origen.fecha(item["ruta"]) or 0)

        nuevo_estado[nombre] = {"sha": item["sha"], "ts": ts}
        fechas[nombre] = ts
        resultado["archivos"].append({"nombre": nombre, "ts": ts,
                                      "nuevo": bool(cambio)})

    if fechas:
        (destino / SIDECAR).write_text(
            json.dumps(fechas, ensure_ascii=False, indent=2), encoding="utf-8")
        _estado_path(slug).write_text(
            json.dumps(nuevo_estado, ensure_ascii=False, indent=2),
            encoding="utf-8")

    _ultima_sync[slug] = time.time()
    return resultado


def asegurar(slug: str, destino: Path) -> dict | None:
    """Sincroniza si no se ha hecho en esta ejecucion (o vencio el TTL)."""
    if not origen.externo():
        return None
    if time.time() - _ultima_sync.get(slug, 0) < _TTL_SEG:
        return None
    return sincronizar(slug, destino)


def sincronizar_todos(proyectos, forzar: bool = False) -> dict[str, dict]:
    """Sincroniza la data de todos los proyectos indicados."""
    return {p.slug: sincronizar(p.slug, p.path / "data", forzar=forzar)
            for p in proyectos}


def estado_por_proyecto(slug: str) -> dict:
    """Ultima sincronizacion conocida (para el panel de administracion)."""
    estado = _leer_json(_estado_path(slug), {})
    ts = max((v.get("ts", 0) for v in estado.values()), default=0)
    return {"archivos": len(estado), "ts": ts,
            "sincronizado": _ultima_sync.get(slug)}
