"""
Analitica de uso de la plataforma: quien entra y que se ve.

Registra dos tipos de evento, sin datos personales mas alla del correo
corporativo que ya usa el inicio de sesion:

    acceso  -> alguien inicio sesion (paso el codigo OTP)
    vista   -> alguien abrio la vista de un dashboard

Los eventos se guardan en memoria y en var/eventos.json, y se replican en
el origen externo (_plataforma/eventos.json) para que sobrevivan a los
reinicios y redeploys de Render, que borran el disco. La escritura remota
va con freno: como maximo una cada PERSISTIR_CADA_SEG segundos.
"""

from __future__ import annotations

import datetime
import threading
import time

from core import origen

ARCHIVO = "eventos.json"
MAX_EVENTOS = 8000            # varios meses de uso interno
PERSISTIR_CADA_SEG = 45

_lock = threading.Lock()
_eventos: list[dict] = []
_cargado = False
_ultimo_guardado = 0.0
_pendientes = 0


# --- Carga y guardado -----------------------------------------------------


def cargar():
    global _eventos, _cargado
    if _cargado:
        return
    with _lock:
        if _cargado:
            return
        datos = origen.leer_estado(ARCHIVO, [])
        _eventos = datos if isinstance(datos, list) else []
        _cargado = True


def guardar(forzar: bool = False) -> bool:
    """Persiste los eventos (con freno, salvo que se fuerce)."""
    global _ultimo_guardado, _pendientes
    ahora = time.time()
    if not forzar and (_pendientes == 0
                       or ahora - _ultimo_guardado < PERSISTIR_CADA_SEG):
        return False
    with _lock:
        copia = list(_eventos[-MAX_EVENTOS:])
    ok = origen.guardar_estado(ARCHIVO, copia)
    _ultimo_guardado = ahora
    _pendientes = 0
    return ok


# --- Registro -------------------------------------------------------------


def instalar_guardado_automatico():
    """Guarda la analitica cuando el servicio se apaga o se duerme.

    Render manda SIGTERM antes de dormir el servicio o redesplegar: ahi se
    fuerza la escritura al origen para no perder la cola de eventos. Nadie
    tiene que pulsar nada nunca.
    """
    import atexit
    import signal

    def _cerrar(*_):
        try:
            guardar(forzar=True)
        finally:
            pass

    atexit.register(_cerrar)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            previo = signal.getsignal(sig)

            def _handler(s, f, _previo=previo):
                _cerrar()
                if callable(_previo):
                    _previo(s, f)
                else:
                    raise SystemExit(0)

            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass  # fuera del hilo principal: basta con atexit


def registrar(tipo: str, correo: str | None = None, slug: str | None = None,
              vista: str | None = None):
    """Anota un evento. Nunca interrumpe la navegacion si algo falla."""
    global _pendientes
    try:
        cargar()
        ev = {"ts": int(time.time()), "tipo": tipo,
              "correo": (correo or "anonimo").lower()}
        if slug:
            ev["slug"] = slug
        if vista:
            ev["vista"] = vista
        with _lock:
            _eventos.append(ev)
            if len(_eventos) > MAX_EVENTOS + 500:
                del _eventos[:-MAX_EVENTOS]
        _pendientes += 1
        # Un inicio de sesión es poco frecuente y demasiado valioso para
        # dejarlo en la cola: se guarda al instante.
        guardar(forzar=(tipo == "acceso"))
    except Exception as e:  # la analitica jamas debe romper una vista
        print("[analitica] no se pudo registrar:", e)


def eventos() -> list[dict]:
    cargar()
    with _lock:
        return list(_eventos)


def borrar_todo() -> bool:
    global _eventos, _cargado
    with _lock:
        _eventos = []
        _cargado = True
    return origen.guardar_estado(ARCHIVO, [])


# --- Resumenes ------------------------------------------------------------


def _dia(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _humano(ts: int | None) -> str:
    if not ts:
        return "—"
    seg = int(time.time()) - ts
    if seg < 90:
        return "hace un momento"
    if seg < 3600:
        return f"hace {seg // 60} min"
    if seg < 86400:
        return f"hace {seg // 3600} h"
    dias = seg // 86400
    if dias == 1:
        return "ayer"
    if dias < 30:
        return f"hace {dias} días"
    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y")


def resumen(dias: int = 30) -> dict:
    """Agrega los eventos de los ultimos `dias` para el panel."""
    todos = eventos()
    ahora = int(time.time())
    corte = ahora - dias * 86400
    corte7 = ahora - 7 * 86400
    periodo = [e for e in todos if e["ts"] >= corte]

    # --- por persona ---
    personas: dict[str, dict] = {}
    for e in todos:
        c = e["correo"]
        p = personas.setdefault(c, {
            "correo": c, "accesos": 0, "vistas": 0, "ultimo": 0,
            "favoritos": {}, "reciente": 0,
        })
        p["ultimo"] = max(p["ultimo"], e["ts"])
        if e["tipo"] == "acceso":
            p["accesos"] += 1
        elif e["tipo"] == "vista":
            p["vistas"] += 1
            if e.get("slug"):
                p["favoritos"][e["slug"]] = p["favoritos"].get(e["slug"], 0) + 1
        if e["ts"] >= corte:
            p["reciente"] += 1
    for p in personas.values():
        top = sorted(p["favoritos"].items(), key=lambda kv: -kv[1])
        p["favorito"] = top[0][0] if top else None
        p["ultimo_humano"] = _humano(p["ultimo"])
        p.pop("favoritos", None)

    # --- por dashboard ---
    tablero: dict[str, dict] = {}
    for e in todos:
        if e["tipo"] != "vista" or not e.get("slug"):
            continue
        d = tablero.setdefault(e["slug"], {
            "slug": e["slug"], "vistas": 0, "vistas_periodo": 0, "vistas_7": 0,
            "personas": set(), "ultima": 0, "por_vista": {},
        })
        d["vistas"] += 1
        d["personas"].add(e["correo"])
        d["ultima"] = max(d["ultima"], e["ts"])
        if e["ts"] >= corte:
            d["vistas_periodo"] += 1
        if e["ts"] >= corte7:
            d["vistas_7"] += 1
        if e.get("vista"):
            d["por_vista"][e["vista"]] = d["por_vista"].get(e["vista"], 0) + 1
    for d in tablero.values():
        d["personas_unicas"] = len(d["personas"])
        d.pop("personas", None)
        d["ultima_humano"] = _humano(d["ultima"])

    # --- serie diaria (para la grafica) ---
    por_dia: dict[str, dict] = {}
    for e in periodo:
        clave = _dia(e["ts"])
        d = por_dia.setdefault(clave, {"accesos": 0, "vistas": 0})
        d["accesos" if e["tipo"] == "acceso" else "vistas"] += 1
    serie = []
    for i in range(dias - 1, -1, -1):
        dia = datetime.datetime.fromtimestamp(ahora - i * 86400)
        clave = dia.strftime("%Y-%m-%d")
        d = por_dia.get(clave, {})
        serie.append({"dia": clave, "etiqueta": dia.strftime("%d/%m"),
                      "accesos": d.get("accesos", 0),
                      "vistas": d.get("vistas", 0)})

    activos = {e["correo"] for e in periodo}
    top_dash = sorted(tablero.values(), key=lambda d: -d["vistas_periodo"])

    return {
        "dias": dias,
        "total_eventos": len(todos),
        "accesos_periodo": sum(1 for e in periodo if e["tipo"] == "acceso"),
        "vistas_periodo": sum(1 for e in periodo if e["tipo"] == "vista"),
        "personas_activas": len(activos),
        "personas": sorted(personas.values(), key=lambda p: -p["ultimo"]),
        "tablero": tablero,
        "top": top_dash[0] if top_dash else None,
        "serie": serie,
        "desde": _humano(min((e["ts"] for e in todos), default=0)),
    }
