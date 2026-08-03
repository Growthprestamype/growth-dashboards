"""
Autenticacion por codigo de un solo uso (OTP) enviado al correo.

Flujo:
  1. La persona ingresa su correo. Debe (a) pertenecer al dominio
     @prestamype.com y (b) estar en la lista de correos permitidos.
  2. Se le envia un PIN de 6 digitos valido por 15 minutos.
  3. Al ingresar el PIN correcto se abre la sesion (cookie firmada,
     7 dias), igual que antes: no se pide PIN en cada visita.
  4. "Salir" cierra la sesion.

Seguridad / diseno:
  - El PIN nunca se guarda: en la sesion viaja solo un HMAC firmado con
    SECRET_KEY (email|pin|vencimiento). Sin la clave del servidor no se
    puede verificar ni forzar offline, y el mecanismo sobrevive a los
    reinicios/siestas de Render free (no depende de memoria).
  - Maximo 5 intentos por PIN y reenvio con espera de 60 segundos.
  - La lista de permitidos se amplia con la variable de entorno
    ALLOWED_EMAILS (correos separados por coma), sin tocar codigo.
  - El correo sale por SMTP (variables SMTP_*). Si SMTP no esta
    configurado (desarrollo), el PIN se imprime en los logs del servidor.

Variables de entorno:
  SECRET_KEY       firma de sesiones y PINs (obligatoria en produccion)
  ALLOWED_EMAILS   p.ej. "aaguirre@prestamype.com,rhinojosa@prestamype.com"

  Envio de correo (en orden de preferencia):
  1) API HTTPS de Brevo — funciona en Render, que bloquea SMTP saliente:
     BREVO_API_KEY   clave API (Brevo -> SMTP y API -> Claves API)
     SMTP_FROM       remitente verificado en Brevo
  2) SMTP clasico (otros hosts): SMTP_HOST, SMTP_PORT, SMTP_USER,
     SMTP_PASSWORD y opcional SMTP_FROM.
  3) Sin nada configurado (desarrollo): el PIN se imprime en los logs.
"""

from __future__ import annotations

import datetime
import hmac
import os
import smtplib
import time
from email.message import EmailMessage
from hashlib import sha256
from secrets import randbelow
from urllib.parse import urlparse

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

auth_bp = Blueprint("auth", __name__)

OPEN_ENDPOINTS = {"auth.login", "auth.enviar", "auth.verificar", "static", "salud"}

DOMINIO = "@prestamype.com"
PERMITIDOS_DEFAULT = [
    "aaguirre@prestamype.com",
    "rhinojosa@prestamype.com",
]
PIN_VIGENCIA_SEG = 15 * 60   # 15 minutos
PIN_INTENTOS_MAX = 5
REENVIO_ESPERA_SEG = 60


# --- Lista de correos permitidos ----------------------------------------


def _permitidos() -> set[str]:
    """Lista efectiva: la variable de entorno mas las altas y bajas que el
    administrador haya hecho desde el panel (core.panel)."""
    try:
        from core import panel
        return panel.permitidos()
    except Exception:
        crudo = os.environ.get("ALLOWED_EMAILS", "")
        if crudo.strip():
            return {e.strip().lower() for e in crudo.split(",") if e.strip()}
        return set(PERMITIDOS_DEFAULT)


def _correo_valido(correo: str) -> tuple[bool, str]:
    correo = (correo or "").strip().lower()
    if not correo:
        return False, "Ingresa tu correo."
    if not correo.endswith(DOMINIO):
        return False, f"Solo se permiten correos {DOMINIO}."
    if correo not in _permitidos():
        return False, ("Este correo no tiene acceso. Pide al administrador "
                       "que te agregue desde el panel.")
    return True, correo


# --- PIN firmado (sin estado en el servidor) -----------------------------


def _mac(correo: str, pin: str, exp: int) -> str:
    clave = (os.environ.get("SECRET_KEY") or "dev").encode()
    mensaje = f"{correo}|{pin}|{exp}".encode()
    return hmac.new(clave, mensaje, sha256).hexdigest()


def _generar_pin() -> str:
    return f"{randbelow(1_000_000):06d}"


def _iniciar_reto(correo: str) -> str:
    pin = _generar_pin()
    exp = int(time.time()) + PIN_VIGENCIA_SEG
    session["otp"] = {
        "correo": correo,
        "exp": exp,
        "mac": _mac(correo, pin, exp),
        "intentos": 0,
        "enviado": int(time.time()),
    }
    return pin


def _verificar_reto(pin_ingresado: str) -> tuple[bool, str]:
    reto = session.get("otp")
    if not reto:
        return False, "Solicita un código primero."
    if time.time() > reto["exp"]:
        session.pop("otp", None)
        return False, "El código expiró. Solicita uno nuevo."
    if reto["intentos"] >= PIN_INTENTOS_MAX:
        session.pop("otp", None)
        return False, "Demasiados intentos. Solicita un código nuevo."

    reto["intentos"] += 1
    session["otp"] = reto  # persistir el contador

    esperado = reto["mac"]
    calculado = _mac(reto["correo"], (pin_ingresado or "").strip(), reto["exp"])
    if hmac.compare_digest(esperado, calculado):
        return True, reto["correo"]

    time.sleep(0.4)  # frena la fuerza bruta en linea
    restantes = PIN_INTENTOS_MAX - reto["intentos"]
    if restantes <= 0:
        session.pop("otp", None)
        return False, "Código incorrecto y sin intentos restantes. Solicita uno nuevo."
    return False, f"Código incorrecto. Te quedan {restantes} intentos."


# --- Envio de correo ------------------------------------------------------


def _cuerpo_html(pin: str) -> str:
    return f"""\
<html><body style="font-family:Arial,Helvetica,sans-serif;color:#2A2925;
background:#FAF7F0;padding:28px">
  <div style="max-width:420px;margin:auto;background:#ffffff;
       border:1px solid #DDD6C6;padding:28px 30px">
    <div style="font-weight:bold;font-size:15px;margin-bottom:4px">
      <span style="display:inline-block;width:11px;height:11px;
        background:#1F5750;border-radius:2px;margin-right:7px"></span>
      Growth Innovation</div>
    <div style="color:#76705F;font-size:12.5px;margin-bottom:22px">
      Experimentos de la Bitacorita</div>
    <div style="font-size:14px;margin-bottom:8px">Tu código de acceso:</div>
    <div style="font-size:34px;font-weight:bold;letter-spacing:8px;
         color:#1F5750;margin-bottom:14px">{pin}</div>
    <div style="color:#76705F;font-size:12.5px">
      Vence en 15 minutos. Si no lo solicitaste, ignora este correo.</div>
  </div>
</body></html>"""


def _cuerpo_texto(pin: str) -> str:
    return (
        "Growth Innovation | Experimentos de la Bitacorita\n\n"
        f"Tu código de acceso es: {pin}\n\n"
        "Vence en 15 minutos. Si no lo solicitaste, ignora este correo."
    )


def _enviar_por_api_brevo(correo: str, pin: str, logger) -> tuple[bool, str | None]:
    """Envio por la API HTTPS de Brevo (puerto 443). Es la via que
    funciona en Render, que bloquea los puertos SMTP salientes."""
    import json
    import urllib.error
    import urllib.request

    api_key = os.environ["BREVO_API_KEY"]
    remitente = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER")
    if not remitente:
        logger.error("BREVO_API_KEY definido pero falta SMTP_FROM (remitente).")
        return False, "falta SMTP_FROM"

    payload = json.dumps({
        "sender": {"name": "Growth Innovation", "email": remitente},
        "to": [{"email": correo}],
        "subject": f"Tu código de acceso: {pin}",
        "htmlContent": _cuerpo_html(pin),
        "textContent": _cuerpo_texto(pin),
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        method="POST",
        headers={
            "api-key": api_key,
            "content-type": "application/json",
            "accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if 200 <= resp.status < 300:
                return True, None
            detalle = resp.read().decode("utf-8", "ignore")[:300]
            logger.error("Brevo respondió %s: %s", resp.status, detalle)
            return False, detalle
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore")[:300]
        logger.error("Brevo HTTP %s: %s", e.code, detalle)
        return False, detalle
    except Exception as e:  # pragma: no cover
        logger.error("Fallo llamando a la API de Brevo: %s", e)
        return False, str(e)


def _enviar_correo(correo: str, pin: str, logger) -> tuple[bool, str | None]:
    # 1) API de Brevo (HTTPS): la via compatible con Render.
    if os.environ.get("BREVO_API_KEY"):
        return _enviar_por_api_brevo(correo, pin, logger)

    # 2) SMTP clasico (otros hosts que si permiten SMTP saliente).
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASSWORD")

    if not (host and user and pwd):
        # 3) Modo desarrollo: el PIN queda en los logs del servidor.
        logger.warning("Envío de correo no configurado. PIN para %s: %s", correo, pin)
        return True, "dev"

    puerto = int(os.environ.get("SMTP_PORT", "587"))
    remitente = os.environ.get("SMTP_FROM", user)

    msg = EmailMessage()
    msg["Subject"] = f"Tu código de acceso: {pin}"
    msg["From"] = remitente
    msg["To"] = correo
    msg.set_content(_cuerpo_texto(pin))
    msg.add_alternative(_cuerpo_html(pin), subtype="html")

    try:
        if puerto == 465:
            with smtplib.SMTP_SSL(host, puerto, timeout=20) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, puerto, timeout=20) as s:
                s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
        return True, None
    except Exception as e:  # pragma: no cover
        logger.error("Fallo el envio de correo a %s: %s", correo, e)
        return False, str(e)


# --- Sesion / utilidades --------------------------------------------------


def is_authenticated() -> bool:
    return bool(session.get("auth"))


def _safe_next(target: str) -> str:
    if not target:
        return "/"
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not target.startswith("/") or target.startswith("//"):
        return "/"
    return target


def _mascara(correo: str) -> str:
    local, _, dom = correo.partition("@")
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'•' * max(len(local) - len(visible), 1)}@{dom}"


# --- Rutas ---------------------------------------------------------------


@auth_bp.route("/login", methods=["GET"])
def login():
    if is_authenticated():
        return redirect(url_for("index"))
    nxt = _safe_next(request.values.get("next", ""))
    if request.args.get("otro") == "1":
        session.pop("otp", None)
    reto = session.get("otp")
    if reto and time.time() <= reto["exp"]:
        return render_template("login.html", paso="pin", error=None,
                               correo_mascara=_mascara(reto["correo"]), next=nxt)
    return render_template("login.html", paso="correo", error=None, next=nxt)


@auth_bp.route("/login/enviar", methods=["POST"])
def enviar():
    from flask import current_app
    nxt = _safe_next(request.form.get("next", ""))
    correo_form = (request.form.get("correo") or "").strip()
    if not correo_form and session.get("otp"):
        # reenvio: reutiliza el correo del reto vigente
        correo_form = session["otp"]["correo"]
    ok, res = _correo_valido(correo_form)
    if not ok:
        return render_template("login.html", paso="correo", error=res, next=nxt)
    correo = res

    # espera minima entre reenvios
    reto = session.get("otp")
    if reto and reto.get("correo") == correo:
        desde = time.time() - reto.get("enviado", 0)
        if desde < REENVIO_ESPERA_SEG:
            faltan = int(REENVIO_ESPERA_SEG - desde)
            return render_template(
                "login.html", paso="pin",
                error=f"Espera {faltan} s para reenviar el código.",
                correo_mascara=_mascara(correo), next=nxt)

    pin = _iniciar_reto(correo)
    enviado, detalle = _enviar_correo(correo, pin, current_app.logger)
    if not enviado:
        session.pop("otp", None)
        return render_template(
            "login.html", paso="correo",
            error="No se pudo enviar el correo. Intenta de nuevo o avisa al administrador.",
            next=nxt)

    aviso = None
    if detalle == "dev":
        aviso = "SMTP no configurado: el código quedó en los logs del servidor."
    return render_template("login.html", paso="pin", error=None, aviso=aviso,
                           correo_mascara=_mascara(correo), next=nxt)


@auth_bp.route("/login/verificar", methods=["POST"])
def verificar():
    nxt = _safe_next(request.form.get("next", ""))
    ok, res = _verificar_reto(request.form.get("pin", ""))
    if not ok:
        reto = session.get("otp")
        if reto:
            return render_template("login.html", paso="pin", error=res,
                                   correo_mascara=_mascara(reto["correo"]), next=nxt)
        return render_template("login.html", paso="correo", error=res, next=nxt)

    correo = res
    session.clear()
    session["auth"] = True
    session["email"] = correo
    session.permanent = True

    from core import analitica, panel
    session["admin"] = panel.es_admin(correo)
    analitica.registrar("acceso", correo=correo)
    return redirect(nxt)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def init_auth(app):
    """Configura sesion, registra rutas y protege toda la app."""
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        secret = os.urandom(32).hex()
        app.logger.warning(
            "SECRET_KEY no definido; usando clave efímera (solo desarrollo)."
        )

    app.secret_key = secret
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not app.debug,
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=7),
    )

    app.register_blueprint(auth_bp)

    @app.before_request
    def _require_login():
        if request.endpoint in OPEN_ENDPOINTS:
            return None
        if is_authenticated():
            return None
        return redirect(url_for("auth.login", next=request.path))
