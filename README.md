# Growth Dashboards

Aplicación web (Flask) para alojar múltiples dashboards de experimentos de
Growth. La portada es un mosaico de experimentos; cada uno tiene sus vistas
(proyección, seguimiento, …). Pensada para vivir en GitHub y desplegarse en
Render.

La idea central: **no se toca el código para sumar un experimento**. Cada
experimento es una carpeta dentro de `projects/` que respeta una convención;
la app la descubre y la publica sola.

## Estructura

```
growth-dashboards/
├── app.py                  # rutas (genéricas, no conocen ningún proyecto)
├── core/registry.py        # descubre las carpetas de projects/
├── core/origen.py          # conexión al origen externo de datos
├── core/datos.py           # sincroniza <origen>/<proyecto>/ -> data/ + fechas
├── core/analitica.py       # eventos de uso (accesos y vistas)
├── core/panel.py           # permisos y estado de dashboards (en caliente)
├── core/admin.py           # panel de administración (/admin)
├── templates/              # base, mosaico (index), shell de dashboard, 404
├── static/css/main.css     # estilo (crema · hueso · gris oscuro · Lato)
├── projects/
│   ├── puesta_en_marcha_ltv/
│   │   ├── meta.json        # ficha: título, subtítulo, vistas, orden
│   │   ├── data/            # datos crudos (Data_2025.csv, Data_2026.csv)
│   │   ├── processor.py     # build() -> {"proyeccion": {...}, "seguimiento": {...}}
│   │   └── templates/
│   │       ├── proyeccion.html
│   │       └── seguimiento.html
│   └── proyecto_demo/        # copia idéntica, solo cambia el nombre de carpeta
├── requirements.txt
├── render.yaml / Procfile / runtime.txt
└── .gitignore
```

## Correr en local

```bash
cd growth-dashboards
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abrir http://127.0.0.1:5000

Para recalcular las métricas de un proyecto sin reiniciar:
añade `?refresh=1` a la URL de una vista.

## Subir a GitHub

```bash
cd growth-dashboards
git init
git add .
git commit -m "Growth Dashboards: estructura inicial + experimento LTV"
git branch -M main
git remote add origin https://github.com/<usuario>/<repo>.git
git push -u origin main
```

## Conectar a Render

1. Render → **New +** → **Web Service** → conecta el repo de GitHub.
2. Render detecta `render.yaml`. Si pide los campos a mano:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Runtime:** Python 3
3. Deploy. Cada `git push` a `main` vuelve a desplegar (autoDeploy).

> Plan Free de Render: el servicio se duerme tras inactividad; la primera
> carga tras dormir tarda unos segundos.

## Origen de los datos (y la fecha que ven las tarjetas)

La data **ya no vive dentro de este repositorio**. La app se conecta a una
ubicación externa organizada con **una carpeta por proyecto, con el nombre
del proyecto**:

```
<origen>/
├── fast_track/
│   ├── Data_Historica.csv
│   └── Data_Seguimiento.csv
├── descuento_en_tasas/
│   └── ...
└── _plataforma/            # lo escribe la app: analítica y permisos
```

Al arrancar (y como máximo cada 15 minutos, o cuando se pulsa **Sincronizar
datos** en el panel), la app baja esos archivos a `projects/<proyecto>/data/`
y deja junto a ellos un `_fechas.json` con la **fecha real de subida de cada
archivo**. Los `processor.py` no cambian: siguen leyendo su carpeta `data/`.

### Por qué todas las tarjetas mostraban la misma fecha

Render clona el repositorio con `--depth 1`. Con un solo commit en la
historia, `git log` devuelve **la misma marca de tiempo para todos los
archivos** (la del último push), y la fecha de modificación en disco es la
del checkout. Por eso, al actualizar un solo CSV, todas las tarjetas se
"actualizaban" juntas.

Ahora la fecha sale, en este orden: `_fechas.json` (la del origen) →
`git log` **solo si el clon tiene historia completa** → fecha del archivo en
disco. Cada proyecto y cada archivo conserva la suya.

### Configuración

| Variable | Para qué |
|---|---|
| `DATA_ORIGEN` | `local` (por defecto), `carpeta`, `dropbox` o `github` |
| `DATA_CARPETA` | Modo `carpeta`: ruta base (disco persistente de Render, unidad de red, carpeta sincronizada de Drive/OneDrive) |
| `DROPBOX_APP_KEY` · `DROPBOX_APP_SECRET` · `DROPBOX_REFRESH_TOKEN` | Modo `dropbox` |
| `DATA_CARPETA_DROPBOX` | **Dejar sin definir** con acceso *App folder*: la raíz ya es la carpeta de la app. Solo se usa para un nivel intermedio |
| `DATA_REPO` | Modo `github`: `usuario/growth-data` |
| `DATA_TOKEN` | Token fino con permiso *Contents: Read and write* sobre ese repo (si no, se usa `GITHUB_TOKEN`) |
| `DATA_RAMA` | Rama del repo de datos (por defecto `main`) |
| `DATA_PREFIJO` | Subcarpeta base dentro del repo, opcional |

### Cuál elegir

| Modo | Cómo se actualiza la data | Costo | Notas |
|---|---|---|---|
| **`dropbox`** | Arrastras el CSV a la carpeta de Dropbox (escritorio, web o celular) **o** lo subes desde el panel | Gratis (2 GB) | La opción más cómoda para el equipo. Dropbox guarda la fecha real de subida por archivo |
| **`carpeta`** | Disco persistente de Render; se sube desde el panel | ~US$ 7/mes de instancia + US$ 0.25/GB | Todo dentro de Render, sin terceros. El disco obliga a una sola instancia |
| **`github`** | Commit en un repo privado de datos | Gratis | Versionado completo, pero maneja CSV como código |
| `local` | Va en el propio repo de la app | Gratis | Comportamiento histórico: **no distingue fechas por archivo** en Render |

**Recomendación: `dropbox`.** Cumple lo que se busca —una carpeta persistente
de la que la web jala directo— sin pagar disco ni tratar los CSV como código.
Se sincroniza desde el escritorio, así que actualizar un dashboard es guardar
el archivo en su carpeta. El modo `carpeta` es la alternativa si se prefiere
no depender de un tercero (requiere plan de pago en Render).

### Configurar Dropbox (una sola vez)

1. Crear una app en https://www.dropbox.com/developers/apps → *Scoped access*
   → *App folder* (queda aislada en su propia carpeta). No hace falta
   configurar *Redirect URI*: el flujo del paso 4 muestra el código en
   pantalla.
2. En la pestaña **Permissions**, marcar estos cuatro permisos y pulsar
   **Submit** (abajo del todo). Si se omite este paso, el token sale sin
   permisos y hay que repetir el paso 4 entero:
   - `account_info.read` — solo para mostrar la cuenta en el panel (opcional)
   - `files.metadata.read` — listar los archivos de cada carpeta
   - `files.content.read` — descargar los CSV
   - `files.content.write` — subir CSV desde el panel
3. En **Settings**, copiar *App key* y *App secret*.
4. Obtener un **refresh token** (dura indefinidamente). Son dos pasos:

   **4.1 · Autorizar en el navegador.** Pega esta dirección reemplazando
   `TU_APP_KEY` por el App key del paso 3 (nada más: no lleva el secret):

   ```
   https://www.dropbox.com/oauth2/authorize?client_id=TU_APP_KEY&response_type=code&token_access_type=offline
   ```

   Dropbox pedirá permiso ("Allow"). Al aceptar muestra un **código** en
   pantalla: cópialo. Dura pocos minutos y sirve UNA sola vez; si algo
   falla, se vuelve a abrir la dirección y se genera otro.

   **4.2 · Canjear el código por el refresh token.** Lo más simple es
   hacerlo desde la propia plataforma: define primero `DROPBOX_APP_KEY` y
   `DROPBOX_APP_SECRET` en Render, entra a **/admin → Conectar Dropbox** y
   sigue los tres pasos: el botón «Autorizar en Dropbox» ya lleva tu App key,
   y al pegar el código la plataforma devuelve el refresh token listo para
   copiar. El App secret nunca sale del servidor.

   Si se prefiere hacerlo a mano, con Python (evita los problemas de
   comillas de curl en Windows):

   ```bash
   python -c "import urllib.request,urllib.parse,base64,json;k='TU_APP_KEY';s='TU_APP_SECRET';c='EL_CODIGO';d=urllib.parse.urlencode({'grant_type':'authorization_code','code':c}).encode();r=urllib.request.Request('https://api.dropboxapi.com/oauth2/token',data=d,headers={'Authorization':'Basic '+base64.b64encode(f'{k}:{s}'.encode()).decode()});print(json.dumps(json.load(urllib.request.urlopen(r)),indent=2))"
   ```

   O con curl (en Git Bash funciona igual):

   ```bash
   curl -u TU_APP_KEY:TU_APP_SECRET \
        -d grant_type=authorization_code -d code=EL_CODIGO \
        https://api.dropboxapi.com/oauth2/token
   ```

   La respuesta trae `access_token` (temporal, se ignora) y
   **`refresh_token`**: ese es el valor de `DROPBOX_REFRESH_TOKEN`.
5. Crear las subcarpetas. Con *App folder*, la carpeta aparece en Dropbox
   como `Aplicaciones/<nombre de la app>` (o `Apps/<nombre>`). Dentro va una
   subcarpeta por proyecto —`fast_track/`, `descuento_en_tasas/`,
   `extension_de_plazos/`, `puesta_en_marcha_ltv/`— y una `_general/` con
   `Data_anual.csv`. El nombre de cada carpeta debe ser **idéntico al slug**
   del proyecto (el nombre de su carpeta en `projects/`).

### Subir datos desde el panel

Con `dropbox` o `carpeta`, el panel de administración incluye **Actualizar
datos**: se elige el dashboard, se suelta el CSV y la app lo guarda en el
origen, resincroniza y recalcula. La fecha de la tarjeta pasa a ser la de esa
subida. No hace falta redeploy ni tocar el repositorio.

Con `DATA_ORIGEN=local` (o sin configurar nada) todo sigue funcionando como
antes, leyendo `projects/<proyecto>/data/`.

## Capas de contexto en las gráficas (la tuerca)

Si existe una base anual del negocio (`_general/Data_anual.csv`), las gráficas
de evolución suman tres capas opcionales, cada una con **su propia escala a la
derecha** para no cruzarse con la del eje izquierdo:

- **Negocio general (casos)**: barras tenues detrás de la serie principal, con
  los casos cerrados de todo el negocio ese mes. Sirve para ver si un mes
  bueno del experimento fue un mes bueno del negocio.
- **Ticket promedio del mes**: marca horizontal sobre las barras (eje derecho
  en soles).
- **Línea base (promedio)**: línea discontinua con el promedio del período de
  la propia serie principal, etiquetada con su valor.

La **tuerca** junto al título de la gráfica permite encender y apagar cada
capa; la elección se recuerda en el navegador. El **embudo**, a su lado,
filtra la data histórica del negocio por **Canal** (Digital / Presencial),
**Moneda** (PEN / USD) y **Esquema** (Cuota Fija, Crédito Puente, …): así se
compara el experimento contra el segmento equivalente y no contra todo el
negocio. Los filtros viajan en la URL (`?canal=Digital&esquema=Cuota+Fija`),
de modo que una vista filtrada se puede compartir tal cual; el embudo se
marca en verde cuando hay algún filtro activo y «Limpiar» los quita. Cada
combinación se cachea por separado. Si un mes no existe en la base
anual (por ejemplo, las vistas de proyección con data de 2025), la capa
simplemente no se dibuja.

La base anual se sube como cualquier otro archivo desde el panel, eligiendo
**Base anual · negocio general**. Columnas que usa: `Periodo de Cierre`
(YYYYMM), `Monto Desembolsado Solarizado` y `Flag Contrato Cerrado`.

## Panel de administración

En `/admin`, visible solo para los correos de `ADMIN_EMAILS`. Responde a:

- **Quiénes entran**: accesos por persona, vistas, actividad reciente y su
  dashboard preferido.
- **Qué se ve más**: vistas por dashboard (7 y 30 días), personas únicas,
  última visita y cuáles no abre nadie.
- **Qué está activo**: cada dashboard se puede **ocultar** (sigue visible
  solo para administradores) o **activar**, y se le puede cambiar la
  **prioridad** con las flechas (manda sobre el `order` del `meta.json`).
- **Permisos**: dar acceso a un correo nuevo, quitárselo a alguien o
  restaurarlo, sin redeploy. `ALLOWED_EMAILS` es la semilla; el panel agrega
  y bloquea encima. Un bloqueo siempre gana.
- **Frescura de la data**: al día (≤10 días), por vencer (≤30) o
  desactualizado, con la fecha real de cada archivo.
- **Actualizar datos**: subir el CSV de un dashboard (o la base anual) al
  origen y recalcular en el momento, sin redeploy.

Ser administrador **solo** se otorga por variable de entorno (`ADMIN_EMAILS`):
no se puede conceder desde la interfaz, así nadie amplía sus propios permisos.

La analítica (`eventos.json`), los permisos (`accesos.json`) y el estado de
los dashboards (`dashboards.json`) se guardan en `_plataforma/` dentro del
origen externo, de modo que sobreviven a los reinicios y redeploys de Render.
Sin origen externo quedan en `var/`, que es efímero.

## Agregar un experimento nuevo

1. Copia una carpeta de `projects/` con un nombre nuevo (sin espacios).
2. Edita su `meta.json` (`slug`, `title`, `subtitle`, `views`, `order`).
3. Pon tus datos en `data/`.
4. Ajusta `processor.py` → `build()` para que devuelva el contexto de cada vista.
5. Ajusta las plantillas en `templates/` (o reutiliza las que ya hay).

Commit + push y aparece solo en el mosaico. No se edita `app.py`.

### Contrato de un proyecto

- `meta.json`: al menos `slug`, `title` y `views` (lista de `{slug, label}`).
- `processor.py`: una función `build()` que devuelve un dict cuyas claves son
  los `slug` de las vistas y cada valor es el contexto que recibe la plantilla.
- `templates/<vista>.html`: extiende `dashboard_base.html` y rellena
  `{% block view %}`.

## Gráficos

`core/charts.py` genera gráficos SVG en el servidor (barras y sparklines), sin
librerías de cliente. Se estilizan con las variables CSS del sitio y se animan
por CSS. Cualquier proyecto puede importarlos:

```python
from core.charts import bar_chart, sparkline
```

El partial `templates/_evolucion.html` arma la sección de evolución mensual a
partir de un dict `evol` (rango, gráfico de volumen y sparklines por métrica),
y se incluye desde las vistas con `{% include "_evolucion.html" %}`.

## Sobre el experimento LTV

- **Proyección** (Data_2025): impacto esperado de ampliar topes de LTV, calculado
  sobre el histórico. Métrica destacada: desembolso adicional anual estimado.
  Conteo de casos: 87 elegibles = 84 cerrados + 3 sin contrato (idéntico a las
  celdas "Cantidad de Casos" de la notebook). Se muestran dos tickets: de casos
  con contrato cerrado y del segmento general.
- **Seguimiento** (Data_2026): impacto real desde el 27-mar-2026, con comparación
  esperado vs. real en conversión, ticket y días de cierre.
- Ambas vistas incluyen la **evolución mensual** agrupada por `Periodo de Cierre`.

La lógica de `processor.py` replica la notebook `Puesta_en_Marcha_LTV.ipynb`.

## Acceso / seguridad

> La lista efectiva de correos con acceso es `ALLOWED_EMAILS` **más** las
> altas y bajas hechas desde `/admin`. Los administradores se definen solo
> con `ADMIN_EMAILS`.


El acceso es por **código de un solo uso (OTP) al correo corporativo**:

1. La persona ingresa su correo `@prestamype.com`, que además debe estar en la
   lista de permitidos (`ALLOWED_EMAILS`, correos separados por coma; si no se
   define, aplica la lista por defecto del código).
2. Recibe un PIN de 6 dígitos por correo, válido por 15 minutos (máx. 5
   intentos, reenvío con espera de 60 s).
3. La sesión queda abierta 7 días en una cookie firmada (HttpOnly, Secure en
   producción). "Salir" en la cabecera cierra la sesión.

El PIN no se guarda en el servidor: viaja como HMAC firmado con `SECRET_KEY`,
por lo que el flujo sobrevive a los reinicios del plan free de Render.

Variables de entorno (Render → Environment):

- `SECRET_KEY` — cadena larga y aleatoria (firma sesiones y PINs).
- `ALLOWED_EMAILS` — lista de correos con acceso. Ampliarla = editar esta
  variable; Render reinicia el servicio al guardar, sin tocar código.
- `BREVO_API_KEY` y `SMTP_FROM` — envío de códigos por la API HTTPS de
  Brevo (la vía que funciona en Render, que bloquea SMTP saliente).
  `SMTP_FROM` debe ser un remitente verificado en Brevo.
- Alternativa para hosts con SMTP saliente permitido: `SMTP_HOST`,
  `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` (y opcional `SMTP_FROM`).

Sin SMTP configurado (desarrollo local), el PIN se imprime en los logs del
servidor para poder probar el flujo.


## Personalización de marca

- **Logo**: reemplaza `static/brand/logo.svg` por el tuyo (mismo nombre de
  archivo). Aparece en la cabecera y en la pantalla de acceso.
- **Imagen de carga**: reemplaza `static/brand/loading.svg`. La animación en
  loop (latido + flotación) la aplica el CSS, así que cualquier imagen que
  pongas quedará animada automáticamente.
- **Paleta**: definida en `static/css/main.css` (`:root`): blanco / blanco
  hueso, verde principal `#00CB75`, verde claro `#B6FFB6` (solo rellenos y
  acentos sobre fondos oscuros) y grises neutros para el texto.

## Pantalla de "waking up" de Render

La página de espera que muestra Render al despertar un servicio del plan free
pertenece al proxy de Render y no se puede rediseñar (aparece antes de que la
app arranque). Dos mitigaciones incluidas:

1. **Keep-alive**: el endpoint público `/salud` responde sin autenticación.
   Configura un monitor gratuito (p. ej. UptimeRobot o cron-job.org) que
   visite `https://<tu-app>.onrender.com/salud` cada 10 minutos y el servicio
   no volverá a dormirse (el plan free incluye 750 h/mes: alcanza para 24/7).
2. **Pantalla de carga propia**: dentro de la app, cualquier navegación que
   tarde más de ~350 ms muestra una capa con tu imagen de
   `static/brand/loading.svg` animada en loop.
