// Iconos, cabecera, selector de video y tarjetas de metricas
// Parte del dashboard de Gondola Inteligente. Se carga desde index.html
// como <script> clasico (no modulo ES): ver el comentario de index.html.

const NOMBRES_LUCIDE_A_PHOSPHOR = {
  'shield-check': 'shield-check', 'sliders': 'faders', 'refresh-cw': 'arrow-clockwise',
  'database': 'database', 'alert-triangle': 'warning', 'help-circle': 'question',
  'clock': 'clock', 'calendar': 'calendar-blank', 'sparkles': 'sparkle',
  'alert-circle': 'warning-circle', 'layers': 'stack', 'tag': 'tag', 'table': 'table',
  'layout-grid': 'squares-four', 'check-circle-2': 'check-circle', 'lightbulb': 'lightbulb',
  'arrow-right': 'arrow-right', 'trending-up': 'trend-up', 'check': 'check', 'x': 'x',
  'server': 'hard-drives', 'map': 'map-pin', 'compass': 'compass',
  'upload': 'upload-simple', 'arrow-left': 'arrow-left',
};

const TAMANO_ICONO_PX = { 'w-3.5': 14, 'w-3': 12, 'w-4': 16, 'w-6': 24, 'w-7': 28, 'w-8': 32 };

function icon(name, cls) {
  cls = cls || '';
  const phosphorName = NOMBRES_LUCIDE_A_PHOSPHOR[name] || name;
  let px = 16;
  for (const clase in TAMANO_ICONO_PX) {
    if (cls.includes(clase)) { px = TAMANO_ICONO_PX[clase]; break; }
  }
  return `<i class="ph-bold ph-${phosphorName} ${cls}" style="font-size:${px}px;line-height:1;display:inline-block"></i>`;
}

// Botoncito "?" para poner junto al titulo de casi cualquier tarjeta del
// dashboard: al pasar el mouse muestra el texto corto (title nativo), y al
// hacer click abre el mismo texto en un modal (renderInfoModal(), en
// vista-modales.js) -pensado para que en pantallas tactiles, donde no hay
// "hover", la explicacion siga siendo alcanzable con un toque. El texto
// vive donde se llama a infoButton(), no en una lista aparte: asi nunca se
// desincroniza el texto del tooltip nativo con el del modal, son el mismo.
function infoButton(titulo, texto) {
  return `<button type="button" data-action="mostrar-info" data-info-titulo="${esc(titulo)}" data-info-texto="${esc(texto)}"
    class="cursor-pointer text-[#A8A29E] hover:text-[#1F6C9F] transition-colors shrink-0"
    title="${esc(texto)}" aria-label="¿De dónde sale este dato?">${icon('help-circle', 'w-3 h-3')}</button>`;
}

// Indicador de estado del backend. El punto es ESTATICO a proposito: no
// parpadea ni late. El estado se comunica con color y etiqueta, que es
// mas rapido de leer y no compite con los datos -el mismo criterio por el
// que se quito el fondo de particulas-. El halo (box-shadow sin
// desplazamiento) hace que el punto se lea como encendido sobre el lienzo
// oscuro sin necesidad de movimiento.
function statusDot(colorVar) {
  return `<span class="w-2 h-2 rounded-full shrink-0" style="background:var(${colorVar});box-shadow:0 0 0 3px color-mix(in srgb, var(${colorVar}) 22%, transparent)"></span>`;
}

function renderHeader() {
  let statusHtml;
  if (state.useMockMode) {
    statusHtml = `<div class="flex items-center gap-2">
      ${statusDot('--warn')}
      <span class="font-bold text-[#956400] text-[11px] tracking-[0.12em] uppercase">Demo activa</span>
    </div>`;
  } else if (state.isCheckingHealth) {
    statusHtml = `<div class="flex items-center gap-2">
      ${icon('refresh-cw', 'w-3 h-3 text-[#787774] animate-spin')}
      <span class="text-[11px] font-bold text-[#787774] tracking-[0.12em] uppercase">Verificando</span>
    </div>`;
  } else if (state.isBackendHealthy) {
    statusHtml = `<div class="flex items-center gap-2">
      ${statusDot('--success')}
      <span class="text-[11px] font-bold text-[#346538] tracking-[0.12em] uppercase">Sistema online</span>
    </div>`;
  } else {
    statusHtml = `<div class="flex items-center gap-2">
      ${statusDot('--danger')}
      <span class="text-[11px] font-bold text-[#9F2F2D] tracking-[0.12em] uppercase">Offline</span>
    </div>`;
  }

  // Botones de icono de la barra: un solo vocabulario para los dos, para
  // que no haya dos formas distintas de "boton de icono" en la misma
  // esquina. 36px de lado: por debajo de eso deja de ser comodo en tactil.
  const iconBtn = (accion, titulo, etiqueta, nombreIcono) => `
    <button type="button" data-action="${accion}"
            class="w-9 h-9 inline-flex items-center justify-center rounded-lg text-[#57534E] hover:text-[#111111] hover:bg-[#EAEAEA]"
            title="${esc(titulo)}" aria-label="${esc(etiqueta)}">
      ${icon(nombreIcono, 'w-4 h-4')}
    </button>`;

  return `
  <header class="sticky top-0 z-30 shrink-0 bg-white border-b border-[#EAEAEA]">
    <!-- Filo de acento: ancla el cian de la marca en la parte mas alta de
         la pantalla y separa la barra del lienzo sin una segunda sombra. -->
    <div style="height:2px;background:linear-gradient(90deg,var(--accent) 0%,var(--accent-2) 46%,transparent 92%)"></div>
    <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 sm:px-6 py-2.5 min-h-16">
      <div class="flex items-center gap-3 min-w-0">
        <button type="button" data-action="volver-inicio"
                class="w-9 h-9 -ml-1 inline-flex items-center justify-center rounded-lg text-[#57534E] hover:text-[#111111] hover:bg-[#EAEAEA] shrink-0"
                title="Volver a la portada" aria-label="Volver a la portada">
          ${icon('arrow-left', 'w-4 h-4')}
        </button>
        <img src="${LOGO_SPLASH}" alt="" class="h-9 sm:h-11 w-auto shrink-0" />
        <div class="min-w-0">
          <!-- El producto es el titulo; el equipo y la version van debajo,
               en la linea de credito. Antes "CodeBolts" era el <h1> y
               "Góndola Inteligente" quedaba enterrado en la letra chica. -->
          <h1 class="text-base sm:text-lg font-bold tracking-[-0.02em] text-[#111111] truncate leading-tight">Góndola Inteligente</h1>
          <p class="text-[11px] truncate leading-tight mt-0.5">
            <span class="marca-equipo">CodeBolts</span>
            <span class="hidden md:inline text-[#787774]"> · v2.4.0</span>
          </p>
        </div>

        <!-- Navegacion de verdad, no botones sueltos por la pantalla.
             Antes "Comparar dos videos" vivia entre los botones de la barra
             de herramientas, mezclado con Subir/PDF/Excel -acciones- pese a
             ser un CAMBIO DE VISTA. Aqui queda claro donde estas parado, y
             la pastilla se desplaza de una opcion a otra en vez de saltar.
             Las dos acciones (cerrar-comparacion / abrir-comparacion) ya
             existian; esto solo les da un sitio decente. -->
        <nav class="seg hidden sm:grid ml-1 lg:ml-3 shrink-0" aria-label="Vistas">
          <span class="seg-pill" style="transform:translateX(${state.mostrandoComparacion ? '100%' : '0'})"></span>
          <button type="button" class="seg-btn" data-action="cerrar-comparacion"
                  aria-current="${state.mostrandoComparacion ? 'false' : 'page'}">
            ${icon('layout-grid', 'w-3.5 h-3.5')} Panel
          </button>
          <button type="button" class="seg-btn" data-action="abrir-comparacion"
                  aria-current="${state.mostrandoComparacion ? 'page' : 'false'}">
            ${icon('trending-up', 'w-3.5 h-3.5')} Comparar
          </button>
        </nav>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <div class="hidden lg:flex items-center gap-1.5 px-2.5 h-8 rounded-lg bg-[#EDF3EC] text-[#346538] border border-[#C7D6C5] text-[11px] font-bold"
             title="El sistema no realiza reconocimiento facial ni almacena datos personales de clientes.">
          ${icon('shield-check', 'w-3.5 h-3.5 text-[#346538] shrink-0')}
          <span>100% anónimo · sin biometría</span>
        </div>
        <div class="flex items-center gap-2 px-3 h-9 rounded-lg bg-[#F3F2EF] border border-[#EAEAEA] shrink-0 whitespace-nowrap">
          ${statusHtml}
        </div>
        ${iconBtn('toggle-dark-mode',
                  state.darkMode ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro',
                  'Cambiar modo claro/oscuro',
                  state.darkMode ? 'sun' : 'moon')}
        ${ES_DESPLIEGUE_PUBLICO ? '' : iconBtn('open-settings', 'Configuración de conexión con la API', 'Configuración de la API', 'sliders')}
      </div>
    </div>
  </header>`;
}

function renderConnectionBanner() {
  if (!state.useMockMode && state.isBackendHealthy === false) {
    return `
    <div class="bg-[#FBF3DB] text-[#956400] px-4 py-2 text-xs border-b border-[#EDD9A3]">
      <div class="max-w-7xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          ${icon('alert-triangle', 'w-4 h-4 text-[#7A5200] shrink-0')}
          <span>No se detecta respuesta en <strong class="font-mono">${esc(state.apiBaseUrl)}</strong> (GET /health).</span>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" data-action="enable-mock" class="underline font-bold hover:text-[#5C3F00]">Activar datos de demostración del contrato</button>
          <span>·</span>
          <button type="button" data-action="retry-health" class="hover:underline flex items-center gap-1">${icon('refresh-cw', 'w-3 h-3')} Reintentar</button>
        </div>
      </div>
    </div>`;
  }
  if (state.useMockMode) {
    return `
    <div class="bg-[#F3F2EF] border-b border-[#EAEAEA] px-4 py-1.5 text-xs text-[#57534E]">
      <div class="max-w-7xl mx-auto flex items-center gap-2">
        ${icon('database', 'w-3.5 h-3.5 text-[#1F6C9F] shrink-0')}
        <span><strong class="text-[#111111]">Modo Demostración Activo:</strong> Respuestas mock que reflejan al 100% el contrato de la API FastAPI.</span>
      </div>
    </div>`;
  }
  return '';
}

function renderVideoSelector() {
  const current = state.videos.find((v) => v.video_id === state.selectedVideoId);
  const isDemo = current ? isDemoVideo(current.video_id) : false;

  const options = `<option value="" ${state.selectedVideoId ? '' : 'selected'}>Elegir un video…</option>` +
    state.videos.map((v) => {
      const demo = isDemoVideo(v.video_id);
      return `<option value="${esc(v.video_id)}" ${v.video_id === state.selectedVideoId ? 'selected' : ''}>${esc(v.source_name || v.video_id)} ${demo ? '(PRUEBA)' : '(Real)'}</option>`;
    }).join('');

  const badge = !current ? '' : isDemo
    ? `<span class="px-2.5 py-1 bg-[#FBF3DB] text-[#956400] text-[10px] font-bold rounded flex items-center gap-1 tracking-wider"
             title="Este video corresponde a un conjunto de prueba/simulación. No refleja una grabación real de tienda.">
        ${icon('alert-circle', 'w-3 h-3 text-[#7A5200] shrink-0')} DATOS DE PRUEBA ACTIVOS
       </span>`
    : `<span class="px-2.5 py-1 bg-[#EDF3EC] text-[#346538] border border-[#C7D6C5] text-[10px] font-bold rounded flex items-center gap-1 tracking-wider"
             title="Video capturado y procesado por el pipeline de visión de la tienda.">
        ${icon('sparkles', 'w-3 h-3 text-[#346538] shrink-0')} PRODUCCIÓN REAL
       </span>`;

  const meta = !current ? '' : `
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 pt-2 lg:pt-0 border-t lg:border-t-0 border-[#F3F2EF] text-[11px] text-[#787774]">
      <div class="flex items-center gap-1" title="Duración del fragmento de video analizado">
        ${icon('clock', 'w-3 h-3 text-[#A8A29E]')}
        <span>Duración: <strong class="text-[#111111] font-semibold">${formatDuration(current.duration_s)}</strong></span>
      </div>
      <span class="w-1 h-1 rounded-full bg-[#D6D3D1] hidden sm:inline-block"></span>
      <div class="flex items-center gap-1" title="Resolución y tasa de cuadros por segundo">
        <span>${current.width}×${current.height} (${current.fps} fps)</span>
      </div>
      <span class="w-1 h-1 rounded-full bg-[#D6D3D1] hidden sm:inline-block"></span>
      <div class="flex items-center gap-1" title="Fecha y hora de procesamiento por el pipeline">
        ${icon('calendar', 'w-3 h-3 text-[#A8A29E]')}
        <span>${formatDateTime(current.processed_at)}</span>
      </div>
    </div>`;

  const errorBox = !state.errorVideos ? '' : `
    <div class="mt-2.5 p-2 rounded-md bg-red-50 border border-red-200 text-xs text-red-800 flex items-start gap-2">
      ${icon('alert-circle', 'w-3.5 h-3.5 text-red-600 shrink-0 mt-0.5')}
      <div><span class="font-semibold">Aviso al cargar videos: </span><span>${esc(state.errorVideos)}</span></div>
    </div>`;

  // Los botones de exportar solo salen si hay un video con datos elegido
  // -exportar un "elige un video" no tiene sentido-. El reporte reutiliza
  // exactamente lo que ya esta en pantalla (ver exportarPDF/exportarCSV,
  // en analisis.js), no arma nada aparte.
  const exportar = !current ? '' : `
    <div class="no-imprimir flex items-center gap-1.5">
      <button type="button" data-action="exportar-pdf"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F3F2EF] hover:bg-[#EAEAEA] rounded-md border border-[#EAEAEA] text-xs font-semibold text-[#2F3437] transition-colors"
              title="Abre el diálogo de impresión del navegador — elige 'Guardar como PDF' ahí">
        ${icon('table', 'w-3.5 h-3.5 text-[#9F2F2D]')} PDF
      </button>
      <button type="button" data-action="exportar-csv"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F3F2EF] hover:bg-[#EAEAEA] rounded-md border border-[#EAEAEA] text-xs font-semibold text-[#2F3437] transition-colors"
              title="Descarga un .csv que Excel abre directamente">
        ${icon('table', 'w-3.5 h-3.5 text-[#346538]')} Excel
      </button>
    </div>`;

  return `
  <div class="no-imprimir bg-white rounded-xl border border-[#EAEAEA] p-3.5 sm:p-4 shadow-xs">
    <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
      <div class="flex-1 flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2 px-3 py-1.5 bg-[#F3F2EF] rounded-md border border-[#EAEAEA] flex-1 sm:flex-initial min-w-[280px]">
          <span class="text-xs font-medium text-[#57534E] uppercase tracking-wider shrink-0">Video:</span>
          <select id="video-select" data-action="select-video" ${state.isLoadingVideos || !state.videos.length ? 'disabled' : ''}
                  class="bg-transparent text-sm font-semibold text-[#2F3437] outline-none cursor-pointer w-full py-0.5">
            ${options}
          </select>
        </div>
        <div class="flex items-center">${badge}</div>
        ${current && !state.useMockMode && current.video_id.startsWith('subido_') ? `
        <button type="button" data-action="eliminar-video" ${state.isDeletingVideo ? 'disabled' : ''}
                class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F3F2EF] hover:bg-[#9F2F2D]/10 rounded-md border border-[#EAEAEA] hover:border-[#9F2F2D]/30 text-xs font-semibold text-[#9F2F2D] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title="Borrar este video de la base de datos y del servidor. No se puede deshacer.">
          ${icon(state.isDeletingVideo ? 'refresh-cw' : 'trash', `w-3.5 h-3.5 ${state.isDeletingVideo ? 'animate-spin' : ''}`)} ${state.isDeletingVideo ? 'Borrando…' : 'Eliminar'}
        </button>` : ''}
        <button type="button" data-action="abrir-comparacion"
                class="sm:hidden inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F3F2EF] hover:bg-[#EAEAEA] rounded-md border border-[#EAEAEA] text-xs font-semibold text-[#2F3437]">
          ${icon('trending-up', 'w-3.5 h-3.5 text-[#1F6C9F]')} Comparar dos videos
        </button>
        ${ES_DESPLIEGUE_PUBLICO ? '' : `
        <button type="button" data-action="abrir-subida" ${state.useMockMode ? 'disabled title="Apaga el Modo Datos de Demostración para subir un video: hace falta la API real."' : ''}
                class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F3F2EF] hover:bg-[#EAEAEA] rounded-md border border-[#EAEAEA] text-xs font-semibold text-[#2F3437] disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
          ${icon('upload', 'w-3.5 h-3.5 text-[#346538]')} Subir video
        </button>`}
        ${exportar}
        <button type="button" data-action="refresh-videos" ${state.isLoadingVideos ? 'disabled' : ''}
                class="inline-flex items-center gap-1 text-xs font-medium text-[#1F6C9F] hover:text-[#18567D] disabled:opacity-50 transition-colors ml-auto sm:ml-0"
                title="Volver a consultar lista de videos en /videos">
          ${icon('refresh-cw', `w-3 h-3 ${state.isLoadingVideos ? 'animate-spin' : ''}`)}
          <span class="text-[11px]">Actualizar</span>
        </button>
      </div>
      ${meta}
    </div>
    ${errorBox}
  </div>
  <div class="solo-imprimir" style="margin-bottom:1.5rem;display:flex;align-items:center;gap:0.85rem;border-bottom:2px solid #111111;padding-bottom:0.85rem">
    <img src="${LOGO_SPLASH}" alt="Góndola Inteligente" style="height:52px;width:auto;flex-shrink:0" />
    <div>
      <h1 style="font-size:1.15rem;font-weight:700;margin:0;line-height:1.2">Góndola Inteligente</h1>
      <p style="font-size:0.75rem;color:#787774;margin:0.15rem 0 0;text-transform:uppercase;letter-spacing:0.05em">Reporte de análisis por video</p>
      ${current ? `<p style="font-size:0.8rem;color:#57534E;margin:0.35rem 0 0">Video: <strong>${esc(current.source_name || current.video_id)}</strong> (${esc(current.video_id)}) — ${isDemo ? 'DATOS DE PRUEBA' : 'Producción real'} — generado ${esc(new Date().toLocaleString('es-CO'))}</p>` : ''}
    </div>
  </div>`;
}

// Las llamadas a metricCard() pasan el color de la barra como hex literal
// (heredado de cuando la paleta vivia repartida por el codigo). Un color en
// `style=""` no lo alcanza ningun selector de clase, asi que se traduce
// AQUI al token del tema. Asi los 12 sitios que llaman a esta funcion no
// cambian, y aun asi la barra sigue al tema claro/oscuro.
const BARRA_A_TOKEN = {
  '#1F6C9F': 'var(--accent-solid)',
  '#346538': 'var(--success-bar)',
  '#B8790B': 'var(--warn-bar)',
  '#9F2F2D': 'var(--danger-bar)',
};

function metricCard({ id, title, value, subtext, badge, tone = 'neutral', tooltip, highlight = false, barColor = '#1F6C9F', progressPercent = 50, countTarget = null, icono = 'layers' }) {
  const toneClasses = { accent: 'text-[#346538]', warning: 'text-[#B8790B]', danger: 'text-[#9F2F2D]', info: 'text-[#1F6C9F]', neutral: 'text-[#787774]' };
  const clamped = Math.min(100, Math.max(0, progressPercent));
  const barra = BARRA_A_TOKEN[barColor] || 'var(--accent)';
  // tracking-[-0.03em]: las cifras grandes piden mas apretado que el texto.
  // tabular-nums evita que el numero "salte" de ancho mientras cuenta.
  const claseValor = 'font-data text-[26px] sm:text-[30px] leading-none font-semibold tracking-[-0.03em] text-[#111111]';
  const valueHtml = countTarget !== null
    ? `<span class="${claseValor}" data-count-target="${countTarget}">0</span>`
    : `<span class="${claseValor}">${value}</span>`;
  // Insignia de color por metrica: cada tarjeta se reconoce de un vistazo
  // por su icono, en vez de ser seis rectangulos identicos. El color sale
  // del MISMO token que su barra, asi que insignia y barra siempre dicen lo
  // mismo -no es decoracion suelta.
  const insignia = `
    <span class="metric-insignia shrink-0" style="--c:${barra}">${icon(icono, 'w-4 h-4')}</span>`;

  return `
  <div id="${id}" class="metric-card p-4 rounded-xl border card-lift flex flex-col justify-between bg-white ${highlight ? 'border-[#1F6C9F]/40 ring-1 ring-[#1F6C9F]/20' : 'border-[#EAEAEA]'}"
       style="--c:${barra}${highlight ? ';box-shadow:0 0 0 1px var(--accent-ring), var(--shadow-card)' : ''}">
    <div class="flex items-start justify-between gap-1.5 mb-3">
      <div class="flex items-center gap-2.5 min-w-0">
        ${insignia}
        <span class="text-[10px] font-bold text-[#787774] uppercase tracking-[0.12em] leading-tight" title="${esc(title)}">${esc(title)}</span>
      </div>
      ${tooltip ? infoButton(title, tooltip) : ''}
    </div>
    <div>
      <div class="flex items-baseline gap-2 flex-wrap">
        ${valueHtml}
        ${badge ? `<span class="text-[11px] font-semibold truncate ${toneClasses[tone]}">${esc(badge)}</span>` : ''}
      </div>
      <p class="text-[11px] text-[#787774] truncate mt-1.5" title="${esc(subtext)}">${esc(subtext)}</p>
    </div>
    <!-- La barra no es adorno: es el valor situado contra su propio techo.
         El riel se ve siempre, para que "casi vacio" se distinga de "sin
         dato" -antes con 0% no se veia nada y parecia que faltaba algo. -->
    <div class="w-full h-1.5 rounded-full overflow-hidden mt-3" style="background:var(--surface-3)">
      <div class="h-full w-full kpi-bar rounded-full" style="transform:scaleX(${clamped / 100});background:${barra}"></div>
    </div>
  </div>`;
}

// Video anonimizado (RENDER_MODE=privacy del AI Service): PILOTO, solo
// para probar si el equipo lo quiere -ver GET /videos/{id}/render en
// backend/api.py-. No existe en modo demo (los datos de MOCK_* no tienen
// ningun archivo de video detras, solo numeros inventados a mano) y no
// todos los videos reales tienen este render generado, por eso el
// manejo de error inline: si el archivo no esta, se oculta el
// reproductor roto y se muestra un aviso en vez de un cuadro negro.
function renderVideoPlayer() {
  // No solo "modo demo global apagado": un video de PRUEBA especifico
  // (video_demo_001/002, fixtures armados a mano en la base de datos, ver
  // isDemoVideo()) tampoco tiene ningun render real detras, aunque el
  // modo demo global este apagado -si no, el reproductor intenta cargar
  // y siempre muestra "no disponible", que no aporta nada a quien esta
  // viendo un dato de prueba a proposito.
  if (!state.selectedVideoId || isDemoVideo(state.selectedVideoId)) return '';
  // El <video> de verdad NO va aqui adentro: vive en #video-player-portal,
  // FUERA de #root (ver el <body> y el comentario grande en reproductor.js,
  // junto a initVideoPlayer()). Este div es solo un HUECO -con una altura
  // fija, para que el portal sepa que tamano ocupar- que reserva el
  // espacio en el layout normal de la pagina.
  return `
  <div class="no-imprimir bg-white rounded-xl border border-[#EAEAEA] p-4 sm:p-5 shadow-xs">
    <div class="flex items-center gap-2.5 mb-3">
      <div class="w-7 h-7 rounded-lg bg-[#F3F2EF] text-[#787774] flex items-center justify-center shrink-0">${icon('video-camera', 'w-4 h-4')}</div>
      <div>
        <h3 class="text-sm font-bold text-[#111111]">Video anonimizado</h3>
        <p class="text-[11px] text-[#787774]">Sin imágenes reales de la tienda — solo la detección</p>
      </div>
    </div>
    <div id="video-player-placeholder" class="w-full rounded-lg bg-[#0B1220]" style="height:400px"></div>
  </div>`;
}

// --------------------------------------------------------------------------
// Barra lateral de secciones del panel.
//
// Antes el panel era UN scroll larguisimo con todo apilado -resumen, zonas,
// mapa de calor, video, retroalimentacion-, y para llegar al mapa de calor
// habia que bajar media pantalla. Ahora cada bloque es una seccion que se
// elige aqui.
//
// Las secciones NO se montan y desmontan: se pintan todas y se oculta la
// que no esta activa (ver .panel-seccion en css/estilos.css). Dos motivos
// concretos: el reporte en PDF (window.print()) imprime la pantalla tal
// cual, y con secciones desmontadas saldria solo la activa -perderia la
// mitad del reporte-; y el <video> del reproductor vive en un portal que se
// posiciona midiendo su hueco, asi que el hueco tiene que existir.
// --------------------------------------------------------------------------
const SECCIONES_PANEL = [
  { id: 'video',    nombre: 'Video',         icono: 'video-camera', pie: 'Render anonimizado' },
  { id: 'resumen',  nombre: 'Resumen',       icono: 'layout-grid',  pie: 'Métricas del video' },
  { id: 'zonas',    nombre: 'Zonas',         icono: 'layers',       pie: 'Góndola y estantes' },
  { id: 'mapa',     nombre: 'Mapa de calor', icono: 'map',          pie: 'Dónde circula la gente' },
  { id: 'reportes', nombre: 'Reportes',      icono: 'table',        pie: 'Cómo leer los números' },
];

function renderNavSecciones() {
  const activa = state.panelSeccion;
  const items = SECCIONES_PANEL.map((s) => {
    const esActiva = s.id === activa;
    return `
      <button type="button" data-action="ir-seccion" data-seccion="${s.id}"
              class="nav-item ${esActiva ? 'nav-item-activo' : ''}"
              ${esActiva ? 'aria-current="page"' : ''}>
        <span class="nav-item-icono">${icon(s.icono, 'w-4 h-4')}</span>
        <span class="min-w-0">
          <span class="nav-item-nombre">${s.nombre}</span>
          <span class="nav-item-pie">${s.pie}</span>
        </span>
      </button>`;
  }).join('');

  return `
  <nav class="no-imprimir panel-nav" aria-label="Secciones del panel">
    <p class="panel-nav-titulo">Análisis</p>
    ${items}
  </nav>`;
}

// Envuelve el contenido de una seccion. `activa` decide cual se ve; las
// demas siguen en el DOM (ver el comentario de arriba).
function seccionPanel(id, contenido) {
  const activa = state.panelSeccion === id;
  const meta = SECCIONES_PANEL.find((s) => s.id === id);
  return `
  <section class="panel-seccion ${activa ? 'activa' : ''}" data-seccion="${id}"
           aria-label="${esc(meta ? meta.nombre : id)}">
    ${contenido}
  </section>`;
}
