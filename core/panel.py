"""
Estado que el administrador puede cambiar en caliente, sin redeploy.

Dos cosas:

  ACCESOS      Quien puede entrar. La variable de entorno ALLOWED_EMAILS
               sigue siendo la semilla; encima de ella el panel permite
               AGREGAR y BLOQUEAR correos. Un bloqueo siempre gana, aunque
               el correo venga en la variable de entorno.

  DASHBOARDS   Que se publica y en que orden. Cada proyecto puede estar
               activo (visible para todos) u oculto (solo administradores,
               util para uno en construccion o ya vencido), y tiene una
               prioridad que manda sobre el "order" de su meta.json.

Todo se guarda en el origen externo (_plataforma/*.json) para sobrevivir
a los reinicios de Render.

Quien es administrador se define SOLO por variable de entorno
(ADMIN_EMAILS). No se puede otorgar desde la interfaz: asi nadie que
entre al panel puede ampliarse privilegios.
"""

from __future__ import annotations

import os
import time

from core import origen

ARCHIVO_ACCESOS = "accesos.json"
ARCHIVO_DASHBOARDS = "dashboards.json"

DOMINIO = "@prestamype.com"

_accesos: dict | None = None
_dashboards: dict | None = None


# --- Administradores (solo variable de entorno) ---------------------------


def admins() -> set[str]:
    crudo = os.environ.get("ADMIN_EMAILS", "")
    return {c.strip().lower() for c in crudo.split(",") if c.strip()}


def es_admin(correo: str | None) -> bool:
    return bool(correo) and correo.strip().lower() in admins()


# --- Accesos --------------------------------------------------------------


def _cargar_accesos() -> dict:
    global _accesos
    if _accesos is None:
        datos = origen.leer_estado(ARCHIVO_ACCESOS, {})
        _accesos = {
            "agregados": list(datos.get("agregados", [])),
            "bloqueados": list(datos.get("bloqueados", [])),
            "registro": list(datos.get("registro", [])),
        }
    return _accesos


def _guardar_accesos() -> bool:
    return origen.guardar_estado(ARCHIVO_ACCESOS, _cargar_accesos())


def _anotar(accion: str, correo: str, por: str):
    reg = _cargar_accesos()["registro"]
    reg.append({"ts": int(time.time()), "accion": accion,
                "correo": correo, "por": por})
    del reg[:-200]


def base_env() -> set[str]:
    """Correos que vienen de la variable de entorno (o el default)."""
    crudo = os.environ.get("ALLOWED_EMAILS", "")
    if crudo.strip():
        return {c.strip().lower() for c in crudo.split(",") if c.strip()}
    return {"aaguirre@prestamype.com", "rhinojosa@prestamype.com"}


def permitidos() -> set[str]:
    """Lista efectiva de correos con acceso."""
    a = _cargar_accesos()
    return ((base_env() | {c.lower() for c in a["agregados"]})
            - {c.lower() for c in a["bloqueados"]})


def agregar_correo(correo: str, por: str) -> tuple[bool, str]:
    correo = (correo or "").strip().lower()
    if not correo.endswith(DOMINIO):
        return False, f"Solo se permiten correos {DOMINIO}."
    a = _cargar_accesos()
    a["bloqueados"] = [c for c in a["bloqueados"] if c.lower() != correo]
    if (correo not in {c.lower() for c in a["agregados"]}
            and correo not in base_env()):
        a["agregados"].append(correo)
    _anotar("alta", correo, por)
    _guardar_accesos()
    return True, f"{correo} ya puede entrar."


def bloquear_correo(correo: str, por: str) -> tuple[bool, str]:
    correo = (correo or "").strip().lower()
    if es_admin(correo):
        return False, "No se puede quitar el acceso a un administrador."
    a = _cargar_accesos()
    if correo not in {c.lower() for c in a["bloqueados"]}:
        a["bloqueados"].append(correo)
    _anotar("bloqueo", correo, por)
    _guardar_accesos()
    return True, f"{correo} quedó sin acceso."


def restaurar_correo(correo: str, por: str) -> tuple[bool, str]:
    correo = (correo or "").strip().lower()
    a = _cargar_accesos()
    a["bloqueados"] = [c for c in a["bloqueados"] if c.lower() != correo]
    _anotar("restauracion", correo, por)
    _guardar_accesos()
    return True, f"{correo} recuperó el acceso."


def quitar_correo(correo: str, por: str) -> tuple[bool, str]:
    """Elimina un correo agregado desde el panel. Los de la variable de
    entorno no se borran: se bloquean."""
    correo = (correo or "").strip().lower()
    a = _cargar_accesos()
    if correo in base_env():
        return bloquear_correo(correo, por)
    a["agregados"] = [c for c in a["agregados"] if c.lower() != correo]
    _anotar("baja", correo, por)
    _guardar_accesos()
    return True, f"{correo} salió de la lista."


def lista_accesos() -> list[dict]:
    """Todos los correos conocidos con su origen y estado."""
    a = _cargar_accesos()
    base = base_env()
    agregados = {c.lower() for c in a["agregados"]}
    bloqueados = {c.lower() for c in a["bloqueados"]}
    return [{
        "correo": correo,
        "origen": "variable de entorno" if correo in base else "panel",
        "bloqueado": correo in bloqueados,
        "admin": es_admin(correo),
    } for correo in sorted(base | agregados | bloqueados)]


def registro_accesos() -> list[dict]:
    return list(reversed(_cargar_accesos()["registro"]))[:12]


# --- Dashboards -----------------------------------------------------------


def _cargar_dashboards() -> dict:
    global _dashboards
    if _dashboards is None:
        datos = origen.leer_estado(ARCHIVO_DASHBOARDS, {})
        _dashboards = datos if isinstance(datos, dict) else {}
    return _dashboards


def _guardar_dashboards() -> bool:
    return origen.guardar_estado(ARCHIVO_DASHBOARDS, _cargar_dashboards())


def estado(slug: str) -> dict:
    return _cargar_dashboards().get(slug, {})


def activo(slug: str) -> bool:
    return bool(estado(slug).get("activo", True))


def orden(slug: str, por_defecto: int) -> int:
    valor = estado(slug).get("orden")
    return int(valor) if valor is not None else por_defecto


def fijar_activo(slug: str, valor: bool, por: str) -> str:
    d = _cargar_dashboards()
    d.setdefault(slug, {}).update(activo=bool(valor),
                                  modificado=int(time.time()), por=por)
    _guardar_dashboards()
    return f"«{slug}» ahora está {'activo' if valor else 'oculto'}."


def fijar_orden(slug: str, valor: int, por: str):
    d = _cargar_dashboards()
    d.setdefault(slug, {}).update(orden=int(valor),
                                  modificado=int(time.time()), por=por)


def mover(slug: str, direccion: int, slugs_ordenados: list[str],
          por: str) -> str:
    """Sube (-1) o baja (+1) un dashboard y reescribe todas las prioridades."""
    if slug not in slugs_ordenados:
        return "Ese dashboard no existe."
    i = slugs_ordenados.index(slug)
    j = i + direccion
    if j < 0 or j >= len(slugs_ordenados):
        return "Ya está en el extremo de la lista."
    nuevo = list(slugs_ordenados)
    nuevo[i], nuevo[j] = nuevo[j], nuevo[i]
    for pos, s in enumerate(nuevo, start=1):
        fijar_orden(s, pos, por)
    _guardar_dashboards()
    return f"«{slug}» {'subió' if direccion < 0 else 'bajó'} de prioridad."
