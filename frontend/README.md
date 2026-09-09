# frontend/

Dashboard de la **Persona 8**: personas detectadas, interacciones, tasa de
rechazo, permanencia promedio y métricas por góndola/estante.

**Consume la API REST de la Persona 7.** No lee los `.jsonl` de `data/output/`
ni consulta PostgreSQL directamente: pide todo por `fetch()` a los endpoints
de `backend/api.py`. La frontera entre capas está en
[`docs/architecture.md`](../docs/architecture.md).

**Probado contra datos reales:** con `video_001` importado (`cd backend &&
python importer.py --video-id video_001`), el dashboard muestra 16 personas, 17
interacciones, 1 pick-up, 0 put-backs y 7.9s de permanencia media —
exactamente los números que devuelve la API. Con una sola interacción
confirmada, varias métricas salen en 0% o "planas": eso es correcto y
honesto (ver "Limitaciones del video actual" más abajo), no un error del
dashboard.

## Aviso sobre el lenguaje: esto NO es Python

El resto del proyecto es Python de punta a punta, y este archivo es la
excepción — es HTML + CSS + JavaScript vanilla. Se dice en voz alta en vez
de esconderlo:

- Se diseñó primero en React (con ayuda de una IA, a partir de un prompt que
  describe el contrato exacto de la API), y después se portó a mano a
  HTML/CSS/JS plano — sin React, sin Node, sin `npm install`, sin paso de
  build — para no romper la regla del equipo de "un solo entorno que
  instalar". No hay ningún `package.json` aquí: `index.html` se abre y ya.
- **Varios archivos, cero build.** `index.html` es solo la cáscara: los
  `<link>`/`<script>` que carga y los tres `<div>`/`<canvas>` que viven
  fuera de `#root` (ver el comentario del propio archivo). Todo el CSS
  vive en `css/estilos.css`, y el JavaScript se reparte en 13 archivos
  bajo `js/` (uno por responsabilidad: estado, cada vista, la subida de
  video, etc. — ver la tabla más abajo). Son `<script src="...">`
  **clásicos**, no módulos ES (`type="module"`): el navegador bloquea los
  módulos ES al abrir un archivo con `file://...` (política CORS), y esta
  página tiene que poder abrirse con doble clic, sin servidor. Los scripts
  clásicos comparten un único ámbito global, igual que si todo siguiera en
  un solo `<script>` — por eso **el orden de los `<script>` en
  `index.html` importa**: hay código de nivel superior que se ejecuta al
  cargar (`const state = ...` en `estado.js` llama a funciones de
  `utils.js`, `const reproductorA = ...` en `reproductor.js` crea el
  portal del video), y un archivo posterior todavía no existe si se mueve
  antes de tiempo. Ningún archivo nuevo pesa más de ~650 líneas: se puede
  seguir abriendo cualquiera y entenderlo sin cargar los otros trece en la
  cabeza.
- Sigue pendiente conectarlo para que **FastAPI lo sirva directamente**
  (`backend/api.py` devolviendo este archivo en `/`), que es justo lo que
  sugiere `docs/architecture.md` para mantener un solo proceso Python
  sirviendo todo. Hoy es un archivo estático suelto, no integrado al backend
  (aunque la API ya tiene CORS habilitado para que esto sea posible, ver
  abajo).

### Los archivos, uno por uno

Orden de carga real en `index.html` (de arriba hacia abajo):

| Archivo | Qué guarda |
|---|---|
| `js/config.js` | `DEFAULT_API_BASE_URL`, `LOGO_SPLASH` (ruta al logo). |
| `js/utils.js` | Formateo (`formatNumber`, `formatDwellTime`, ...), `VIDEOS_DE_PRUEBA_CONOCIDOS`/`isDemoVideo()`, `SUBIDA_VACIA()`, y las rutas (`RUTAS`, `rutaActual()`, `irA()`, `sincronizarConRuta()`). |
| `js/datos-demo.js` | Los datos inventados a mano del Modo Demostración (`MOCK_VIDEOS`, `MOCK_METRICS`, `MOCK_POSITIONS`, ...). |
| `js/api.js` | Las únicas funciones que llaman a `fetch()` contra `backend/api.py`. |
| `js/estado.js` | `const state = {...}`, `setState()`, y todo lo que carga datos y los mete en `state` (`loadVideos`, `loadCompareData`, `arrancar()`, ...). |
| `js/vista-panel.js` | Iconos (`icon()`), cabecera, selector de video, tarjetas de métricas. |
| `js/reproductor.js` | El "portal" del `<video>` anonimizado (ver más abajo) y `ocultarReproductores()`. |
| `js/analisis.js` | `bundleDe()`, la retroalimentación automática (lógica pura) y exportar a CSV. |
| `js/vista-comparar.js` | La vista de comparar dos videos. |
| `js/vista-zonas.js` | Tarjetas de resumen, análisis por zona y el mapa de calor real. |
| `js/subida.js` | Las seis pantallas del modal "Subir video". |
| `js/vista-modales.js` | El modal de configuración y la portada de bienvenida. |
| `js/app.js` | `render()` (arma la pantalla completa desde `state`), los `addEventListener` de clic/input/cambio, y las tres líneas finales que arrancan todo. |

`css/estilos.css` trae todo el CSS (incluido el modo oscuro), `assets/logo.png`
el logo de la portada, y `vendor/tailwindcss-3.4.17.js` el bundle de
Tailwind vendorizado (ver "Qué instalar", más abajo).

## Qué hace

- Portada de bienvenida (`renderPantallaInicio()`) al abrir el archivo: el
  logo, un resumen de qué hace el proyecto y qué puede hacer, y un botón
  "Entrar al panel". Es una portada, no una pantalla de carga: no vuelve a
  aparecer hasta que se recarga la página.
- Selector de video, con etiqueta clara de si son datos reales o de prueba.
  La etiqueta NO se basa en el prefijo del `video_id` (se rompía con videos
  reales importados como `video_demo_merl_*`, del dataset MERL Shopping
  Dataset): en modo demo usa el prefijo `video_demo_`, conectado a la API
  real es al revés -una lista corta y fija de los DOS `video_id` ficticios
  de `backend/database/seed_example.sql` (`VIDEOS_DE_PRUEBA_CONOCIDOS` en
  `index.html`)-, así que cualquier video que de verdad pasó por el
  pipeline se etiqueta "Real" sin que nadie tenga que mantener una lista
  cada vez que alguien procesa uno nuevo.
- Subir un video desde el propio navegador (botón "Subir video"): sube el
  archivo, el servidor lo revisa (abre, dura entre 5 s y 15 min, YOLO
  encuentra personas), la persona dibuja los estantes sobre un fotograma
  sin gente, y desde ahí la API lanza sola la cadena completa y lo importa
  -sin tocar la terminal ni copiar archivos a mano-. Ver
  `backend/uploads.py` y la sección "Subida de video" de
  `backend/README.md`.
- Resumen general (personas, interacciones, pick-ups, put-backs, tasa de
  rechazo, permanencia media), con los números animados al cargar (cuentan
  hacia arriba, no aparecen de golpe).
- Métricas por zona (tabla si hay 2+ zonas, tarjetas si hay 1 sola).
- Una sección de "Diagnóstico de Space Management": frases generadas por
  reglas simples a partir de los números reales (no inventa datos; si no hay
  evidencia suficiente, no dice nada). No es el motor de recomendaciones con
  nivel de confianza que describe el reto — es un primer paso, más simple.
- Mapa de calor real, por coordenadas: consume `GET /videos/{id}/positions`
  (el punto de apoyo — los pies — de cada evento, en píxeles del frame
  original) y pinta una densidad continua con [heatmap.js](https://www.patrick-wied.at/static/heatmapjs/)
  (CDN), no un agregado coloreado por zona. Cada punto se reescala del
  tamaño del frame original al tamaño en pantalla del contenedor
  (`pintarHeatmap()` en `index.html`, con 4 estilos intercambiables y una
  animación de "parpadeo" por punto, además de modo oscuro). Debajo sigue el "Resumen por
  Zona" (antes se llamaba "Mapa de Calor de Zonas"): tarjetas por
  góndola/estante y el ranking de interacción — sigue siendo útil como
  agregado, pero ya no es lo único que hay.
- Modo demostración con datos **inventados a mano** (para explorar la
  interfaz sin tener la API corriendo) — dos videos ficticios,
  `video_demo_pasillo_01` y `video_demo_cabecera`, con números que no salen
  de ningún video ni cálculo real. Siempre etiquetados como prueba en la UI.
  Un modal (ícono ⚙️ en el header) permite apagar el modo demo, cambiar la
  URL de la API o probar la conexión.
- Video anonimizado embebido: `GET /videos/{id}/render` reproducido en un
  `<video>` normal. Sobre el fondo gris inventado (cero píxeles reales, ver
  `ai-service/gondola/video/render.py`) se dibujan los rectángulos de las
  zonas de la calibración -con su nombre, y coloreados de frío a cálido
  según su actividad, el mapa de calor del reto visible directamente en el
  video- y una silueta simple (cabeza + cuerpo, sin ningún rasgo) por cada
  persona detectada, con su zona y permanencia acumulada al lado ("Persona
  3 · Estante 2 · 12.4s"). La caja cambia de color y anuncia el evento un
  instante cuando hay un PICK_UP/PUT_BACK/APPROACH, y la cabecera trae los
  contadores acumulados de personas, interacciones, pick-ups y put-backs.
  Pedido explícito: antes eran cajas de color flotando sobre una rejilla
  vacía, y alguien sin contexto del proyecto no entendía qué estaba viendo.
  El `<video>` vive en un "portal" fuera de `#root`
  (`crearReproductorPersistente()` en `js/reproductor.js`), no dentro de
  la plantilla que se reconstruye en cada `render()`: si viviera ahí
  adentro, cada dato nuevo que llega (zonas, posiciones, métricas llegan
  por separado) interrumpía la descarga a medias y el navegador la
  reportaba como error aunque el servidor respondiera bien — bug real, ya
  resuelto. Otro bug real del mismo portal, encontrado por un compañero de
  equipo: el `<video>` quedaba flotando SOBRE la portada y ATRAVESANDO los
  modales -`#root` tiene `position:relative` + `z-index:1`, y eso lo
  vuelve su PROPIO contexto de apilamiento: cualquier `z-index` de un
  modal de adentro (`z-50`, lo que sea) queda atrapado ahí, comparándose
  solo contra otros hijos de `#root`, nunca contra un HERMANO como el
  portal-. Subir el `z-index` del modal no arregla nada (sigue adentro de
  `#root`), y bajar el del portal lo esconde detrás del fondo opaco de su
  propio placeholder (otro bug real, ya visto en pantalla: un rectángulo
  negro sólido en vez del video). La solución real es más simple que
  mover nada de sitio: `initVideoPlayer()` esconde los dos reproductores
  (`ocultarReproductores()`) mientras cualquier modal esté abierto
  (`state.isConfigModalOpen || state.subida.abierto`) — detrás de un modal
  no se ve igual de todos modos.
- Botón "Atrás" del navegador: antes sacaba de la página entera (nunca se
  agregaba nada al historial). Ahora `#/inicio`, `#/panel` y `#/comparar`
  son tres rutas de verdad en la URL (`RUTAS`/`rutaActual()`/`irA()` en
  `js/utils.js`): cambiar de pantalla cambia el hash, y eso ya agrega una
  entrada al historial por su cuenta, así que el navegador tiene una
  entrada real a la que volver en cada paso, en vez de saltar directo a
  la portada desde cualquier pantalla. Antes comparar compartía la misma
  ruta (`#/panel`) que el video único; se separó a pedido explícito, para
  que el historial distinga las tres pantallas.
- "Retroalimentación": explica en lenguaje llano por qué salen ciertos
  números (tasas en 0%, conteos que no cuadran, video demasiado corto),
  sin tener que ver el video completo. Reglas simples sobre los números ya
  calculados, nada de IA (`generarNotasFeedback()`).
- **Comparar dos videos**, en su propio apartado (botón junto al selector,
  no una tarjeta más de la pantalla principal — mezclar los dos causaba el
  mismo bug de video en blanco que arriba). Trae el paquete completo de
  cada video (`loadCompareData()`) y muestra, lado a lado: resumen general,
  análisis por zona, mapa de calor, resumen por zona y retroalimentación —
  no solo 4 números sueltos. El mismo video no se puede elegir en los dos
  lados a la vez.
- **Exportar a PDF y Excel** (botones junto al selector, solo si hay un
  video elegido): PDF usa `window.print()` con una hoja de estilos de
  impresión que oculta botones/navegación y agrega un encabezado de
  reporte — el texto queda seleccionable en el PDF, no es una captura de
  pantalla. Excel descarga un `.csv` (sin librerías nuevas) con el mismo
  resumen, tabla por zona y retroalimentación que se ve en pantalla.

### Sistema de diseño (para quien lo siga tocando)

- **Paleta:** monocromo cálido (blanco hueso `#F7F6F3`, texto `#111111`) +
  4 acentos pastel desaturados (azul `#1F6C9F`, verde `#346538`, rojo
  `#9F2F2D`, amarillo `#956400`). No es la paleta azul/gris fría con la que
  arrancó el primer borrador — se cambió a propósito, siguiendo principios
  de diseño minimalista. Si vas a agregar un color nuevo, usa uno de estos
  cuatro o uno igual de desaturado; no metas un color saturado nuevo.
- **Iconos:** [Phosphor](https://phosphoricons.com) peso Bold, vía CDN
  (`unpkg.com/@phosphor-icons/web`). El mapeo de nombres viejos (Lucide, de
  cuando se portó desde React) a nombres de Phosphor está en
  `NOMBRES_LUCIDE_A_PHOSPHOR`, en `js/vista-panel.js`. **Ojo:** no se pudo
  verificar el 100% de esos nombres contra el catálogo oficial de Phosphor
  con certeza absoluta — si un ícono aparece en blanco, revisa ese mapeo.
- **Animaciones:** una sola curva de easing (`--ease`, en `css/estilos.css`)
  para toda la interfaz. Números que cuentan (`fillCountUps`/`animateCount`,
  en `js/app.js`), entrada escalonada al cargar (`.stagger-in`, solo la
  primera vez, no en cada render), tarjetas que se levantan al hover
  (`.card-lift`). Respeta `prefers-reduced-motion`.
- **Logo:** imagen generada por IA (una góndola en línea azul/morada),
  procesada a mano para quitarle el fondo (llegó como JPG con un
  cuadriculado "quemado" en los píxeles, sin transparencia real — se limpió
  con una técnica de clave de color, quedándose solo con lo azul/morado
  saturado). Vive como archivo aparte, `assets/logo.png` (referenciado por
  `LOGO_SPLASH` en `js/config.js`), no incrustado como base64 dentro de un
  `<script>` — un archivo binario de ~260 KB no le hace ningún bien al
  tamaño de un script, y el navegador lo cachea aparte del resto del código.

## Qué NO hace todavía

- No está conectado a `backend/api.py` como servidor (ver aviso arriba).
- No hay motor de recomendaciones real con nivel de confianza (Fase 1-2 de
  la Persona 8 en los prompts del equipo).
- No hay optimización para ejecución *edge* ni contenedor Docker.
- No hay integración de extremo a extremo ni pruebas de robustez.
- El mapa de calor por coordenadas no dibuja los contornos de las góndolas
  ni del piso de la tienda sobre la densidad (solo el fondo oscuro liso):
  falta un plano de referencia para superponer.
- Exportar a PDF/Excel solo existe en el panel de un solo video, no en la
  vista de comparación.

## Limitaciones del video actual (`video_001`)

No es un problema del dashboard: son limitaciones reales del video y del
pipeline que el dashboard simplemente refleja con honestidad.

- El video dura solo 3.4 minutos (16 personas). Con tan pocas personas,
  cualquier tasa se ve "plana" (0% o 100%): no hay suficiente muestra para
  que un porcentaje intermedio signifique algo.
- La cámara es **cenital** (vista desde arriba), lo que limita cuánto puede
  detectar `interact.py` (etapa de Persona 5): de 65 gestos candidatos de
  "tomar producto" en todo el video, solo 1 sobrevivió como PICK_UP
  confirmado. El resto no llegó a candidatearse porque, desde arriba, un
  brazo que se estira no ensancha la silueta de la persona como lo haría
  una cámara lateral.
- **Para números menos planos hace falta un video nuevo**, con cámara
  lateral o de 3/4 (no cenital) y más duración. Cuando exista, se vuelve a
  correr la cadena completa (`detect → track → zones → interact → metrics`
  en `ai-service/`, después `python importer.py --video-id <id>` en
  `backend/`) y el dashboard se actualiza solo con el video que elijas del
  selector.

## Qué instalar

**Nada localmente.** No hay `npm install`, no hay build.

**Tailwind CSS ya NO depende de internet**: el bundle del Play CDN vive
como archivo local, `vendor/tailwindcss-3.4.17.js`, cargado con un
`<script src="vendor/tailwindcss-3.4.17.js">` normal en vez de
`<script src="https://cdn.tailwindcss.com">`. Motivo real: algunas redes
(campus, corporativas) bloquean por DNS ese dominio específico, y sin él
toda la página se veía sin un solo estilo -bug encontrado en la práctica
por un compañero de equipo en otra máquina/red-. A diferencia de la
primera versión (pegada inline dentro de un `<script>` de `index.html`,
sin versión fijada), este archivo trae la versión exacta en el propio
nombre (`3.4.17`, la misma que servía el Play CDN) — el `tailwind.config`
en `index.html` sigue siendo formato v3, así que si algún día se
actualiza el archivo hace falta revisar que siga siendo v3, no v4 (que
configura con `@theme` en CSS, no con `tailwind.config`).

La primera vez que se abre, sí hace falta **conexión a internet** para lo
que queda por CDN:

| Qué | De dónde | Versión fijada |
|---|---|---|
| Fuente Plus Jakarta Sans | `https://fonts.googleapis.com` | Estable por diseño de Google Fonts. |
| Iconos Phosphor | `https://unpkg.com/@phosphor-icons/web` | **No.** Siempre trae la última. |
| heatmap.js (mapa de calor) | `https://cdn.jsdelivr.net/npm/heatmap.js@2.0.5/...` | **Sí,** `2.0.5`. |

Sin internet, la página carga y ya se ve con los estilos de Tailwind
puestos (vendorizado), pero sin la fuente, sin iconos y sin mapa de calor.

## Cómo correrlo

1. Abre `frontend/index.html` directamente con doble clic (o arrástralo a
   una pestaña del navegador).
2. Arranca en **Modo Demostración** (datos inventados), para que la
   interfaz sea usable sin nada más corriendo.
3. Para ver datos reales: levanta la API (`cd backend && uvicorn api:app
   --host 0.0.0.0 --port 8000`, ver `backend/database/README.md` para la
   base de datos), abre el ícono de ajustes (⚙️, arriba a la derecha) y
   apaga "Modo Datos de Demostración".

### CORS: ya resuelto

`backend/api.py` tiene `CORSMiddleware` con una lista de orígenes
permitidos (`ORIGENES_PERMITIDOS`, ver el docstring de ese archivo y la
sección "CORS" de `backend/README.md`) — `null` (este `index.html` abierto
como archivo, que manda `Origin: null` en cada `fetch()`) y
`localhost`/`127.0.0.1` (servido por HTTP). Ya **no** es `allow_origins=["*"]`:
desde que existe `POST /uploads` (un endpoint que escribe, no solo lee),
un `"*"` dejaría que cualquier página que alguien de la tienda visitara en
su navegador disparara esos endpoints contra `127.0.0.1` sin que la
persona se enterara. Si abrir `index.html` como archivo y apuntarlo a la
API real falla por política CORS del navegador, confirma primero que la
API esté corriendo con los cambios más recientes de `api.py`.
