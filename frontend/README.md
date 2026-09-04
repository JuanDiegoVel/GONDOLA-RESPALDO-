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
excepción — es HTML + CSS + JavaScript vanilla (`index.html`, un solo
archivo, ~1200 líneas). Se dice en voz alta en vez de esconderlo:

- Se diseñó primero en React (con ayuda de una IA, a partir de un prompt que
  describe el contrato exacto de la API), y después se portó a mano a
  HTML/CSS/JS plano — sin React, sin Node, sin `npm install`, sin paso de
  build — para no romper la regla del equipo de "un solo entorno que
  instalar". No hay ningún `package.json` aquí: `index.html` se abre y ya.
- Sigue pendiente conectarlo para que **FastAPI lo sirva directamente**
  (`backend/api.py` devolviendo este archivo en `/`), que es justo lo que
  sugiere `docs/architecture.md` para mantener un solo proceso Python
  sirviendo todo. Hoy es un archivo estático suelto, no integrado al backend
  (aunque la API ya tiene CORS habilitado para que esto sea posible, ver
  abajo).

## Qué hace

- Selector de video, con etiqueta clara de si son datos reales o de prueba
  (`video_id` que empieza por `video_demo_` → "PRUEBA"; cualquier otro →
  "PRODUCCIÓN REAL").
- Resumen general (personas, interacciones, pick-ups, put-backs, tasa de
  rechazo, permanencia media), con los números animados al cargar (cuentan
  hacia arriba, no aparecen de golpe).
- Métricas por zona (tabla si hay 2+ zonas, tarjetas si hay 1 sola).
- Una sección de "Diagnóstico de Space Management": frases generadas por
  reglas simples a partir de los números reales (no inventa datos; si no hay
  evidencia suficiente, no dice nada). No es el motor de recomendaciones con
  nivel de confianza que describe el reto — es un primer paso, más simple.
- Espacio reservado y claramente etiquetado ("PRÓXIMAMENTE") para el mapa de
  calor: la API todavía no expone coordenadas para pintarlo, así que no se
  inventa uno.
- Modo demostración con datos **inventados a mano** (para explorar la
  interfaz sin tener la API corriendo) — dos videos ficticios,
  `video_demo_pasillo_01` y `video_demo_cabecera`, con números que no salen
  de ningún video ni cálculo real. Siempre etiquetados como prueba en la UI.
  Un modal (ícono ⚙️ en el header) permite apagar el modo demo, cambiar la
  URL de la API o probar la conexión.

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
  `NOMBRES_LUCIDE_A_PHOSPHOR` dentro de `index.html`. **Ojo:** no se pudo
  verificar el 100% de esos nombres contra el catálogo oficial de Phosphor
  con certeza absoluta — si un ícono aparece en blanco, revisa ese mapeo.
- **Animaciones:** una sola curva de easing (`--ease`, en el `<style>`) para
  toda la interfaz. Números que cuentan (`fillCountUps`/`animateCount`),
  entrada escalonada al cargar (`.stagger-in`, solo la primera vez, no en
  cada render), tarjetas que se levantan al hover (`.card-lift`). Respeta
  `prefers-reduced-motion`.
- **Logo:** imagen generada por IA (una góndola en línea azul/morada),
  procesada a mano para quitarle el fondo (llegó como JPG con un
  cuadriculado "quemado" en los píxeles, sin transparencia real — se limpió
  con una técnica de clave de color, quedándose solo con lo azul/morado
  saturado). Está incrustada como base64 dentro de `index.html`, no es un
  archivo aparte.

## Qué NO hace todavía

- No está conectado a `backend/api.py` como servidor (ver aviso arriba).
- No hay motor de recomendaciones real con nivel de confianza (Fase 1-2 de
  la Persona 8 en los prompts del equipo).
- No hay optimización para ejecución *edge* ni contenedor Docker.
- No hay integración de extremo a extremo ni pruebas de robustez.
- El mapa de calor es un espacio reservado, no una funcionalidad.

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

**Nada localmente.** No hay `npm install`, no hay build. Solo hace falta un
navegador moderno y, la primera vez que se abre, **conexión a internet**:
la página carga estas tres cosas desde CDN público en vez de traerlas
empaquetadas:

| Qué | De dónde | Versión fijada |
|---|---|---|
| Tailwind CSS | `https://cdn.tailwindcss.com` | **No.** Siempre trae la última. |
| Fuente Plus Jakarta Sans | `https://fonts.googleapis.com` | Estable por diseño de Google Fonts. |
| Iconos Phosphor | `https://unpkg.com/@phosphor-icons/web` | **No.** Siempre trae la última. |

**Gap conocido, a diferencia del resto del proyecto:** `ai-service` y
`backend` fijan la versión exacta de cada dependencia
(`requirements.txt`/`requirements-dev.txt`). Aquí no se pudo hacer lo mismo
sin arriesgarse a romper la carga del CDN sin poder verificarlo visualmente
en esta sesión. Si Tailwind o Phosphor sacan una versión que cambia algo,
esta página lo hereda sin aviso. Quien siga con esto debería fijar
versiones exactas en las URLs (`cdn.tailwindcss.com/<version>`,
`@phosphor-icons/web@<version>`) la próxima vez que lo toque, y confirmarlo
abriendo la página.

Sin internet, la página carga pero se ve sin estilos ni iconos (el HTML y
el JavaScript sí son locales, autocontenidos).

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

`backend/api.py` tiene `CORSMiddleware` con `allow_origins=["*"]` (ver el
docstring de ese archivo para el porqué). Antes de este cambio, abrir
`index.html` como archivo local y apuntar a la API real fallaba por
política CORS del navegador aunque el servidor respondiera bien. Ya no
debería pasar; si vuelve a pasar, confirma que la API esté corriendo con
los cambios más recientes de `api.py`.
