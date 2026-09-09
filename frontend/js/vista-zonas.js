// Tarjetas de resumen, analisis por zona y mapa de calor
// Parte del dashboard de Gondola Inteligente. Se carga desde index.html
// como <script> clasico (no modulo ES): ver el comentario de index.html.

function renderSummaryCards(bundle = bundleDe(), idPrefix = '') {
  if (bundle.isLoadingDetail || !bundle.detail) {
    if (!bundle.isLoadingDetail) return '';
    const skeletons = Array.from({ length: 6 }).map(() => `
      <div class="h-28 bg-white p-4 rounded-xl border border-[#EAEAEA] flex flex-col justify-between shadow-xs overflow-hidden">
        <div class="h-3 skeleton rounded w-20"></div>
        <div class="h-7 skeleton rounded w-16"></div>
        <div class="w-full bg-[#F3F2EF] h-1 rounded-full"></div>
      </div>`).join('');
    return `<div class="grid gap-3 sm:gap-4 ${idPrefix ? 'grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3' : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6'}">${skeletons}</div>`;
  }

  const d = bundle.detail;
  const rejection = calculateRejectionRate(d.put_back_count, d.pick_up_count);
  const interactionRateVal = d.people_count > 0 ? Math.min(100, Math.round((d.interaction_count / d.people_count) * 100)) : 0;
  const pickUpProgress = d.interaction_count > 0 ? Math.min(100, Math.round((d.pick_up_count / d.interaction_count) * 100)) : (d.pick_up_count > 0 ? 50 : 0);
  const putBackProgress = d.pick_up_count > 0 ? Math.min(100, Math.round((d.put_back_count / d.pick_up_count) * 100)) : 0;
  const dwellProgress = Math.min(100, Math.round(((d.average_dwell_time_s || 0) / 20) * 100));
  const mid = (nombre) => idPrefix ? `metric-${idPrefix}-${nombre}` : `metric-${nombre}`;

  return `
  <section aria-labelledby="kpi-summary-heading${idPrefix}" class="space-y-2">
    <div class="flex items-center justify-between px-1">
      <h2 id="kpi-summary-heading${idPrefix}" class="text-[10px] font-bold text-[#787774] uppercase tracking-[0.1em]">Resumen General del Video</h2>
      <span class="text-[11px] text-[#787774]">Grabación: <code class="font-mono text-[#111111]">${esc(d.video_id)}</code></span>
    </div>
    <!-- En la vista de comparacion cada columna ocupa media pantalla: seis
         tarjetas ahi dejaban ~110px por tarjeta y los titulos se partian
         ("PICK-/UPS", "TASA / RECHAZO") con los subtextos cortados. Con
         idPrefix (o sea, dentro de comparar) se baja a 2-3 columnas. -->
    <div class="kpi-grid grid gap-3 sm:gap-4 ${idPrefix ? 'grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3' : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6'}">
      ${metricCard({ id: mid('people-count'), icono: 'users-three', title: 'Tráfico Total', value: formatNumber(d.people_count), countTarget: d.people_count, subtext: 'personas detectadas', badge: '100% Anónimo', tone: 'neutral', barColor: '#1F6C9F', progressPercent: d.people_count > 0 ? 65 : 0, tooltip: 'Conteo de identificadores de seguimiento únicos (track_id temporales) detectados en el área del pasillo.' })}
      ${metricCard({ id: mid('interaction-count'), icono: 'chat-circle-dots', title: 'Interacciones', value: formatNumber(d.interaction_count), countTarget: d.interaction_count, subtext: `${interactionRateVal}% rate`, badge: `${d.people_count > 0 ? (d.interaction_count / d.people_count).toFixed(1) : '0'} / pers`, tone: 'info', barColor: '#1F6C9F', progressPercent: interactionRateVal, tooltip: 'Eventos donde un cliente se detuvo dentro de la zona de atención de la góndola.' })}
      ${metricCard({ id: mid('pick-up-count'), icono: 'hand-grabbing', title: 'Pick-ups', value: formatNumber(d.pick_up_count), countTarget: d.pick_up_count, subtext: 'productos tomados', badge: 'Extracción', tone: 'accent', barColor: '#1F6C9F', progressPercent: pickUpProgress, tooltip: 'Veces que la mano de un cliente tomó un producto de la góndola según el modelo de interacción.' })}
      ${metricCard({ id: mid('put-back-count'), icono: 'arrow-u-down-left', title: 'Put-backs', value: formatNumber(d.put_back_count), countTarget: d.put_back_count, subtext: 'devoluciones', badge: d.put_back_count === 0 ? '0 devueltos' : `${d.put_back_count} reposiciones`, tone: d.put_back_count === 0 ? 'accent' : 'danger', barColor: '#9F2F2D', progressPercent: putBackProgress, tooltip: 'Veces que un producto previamente levantado fue colocado nuevamente en la góndola.' })}
      ${metricCard({ id: mid('rejection-rate'), icono: 'gauge', title: 'Tasa Rechazo', value: rejection.label, subtext: rejection.rate === null ? 'sin tomas' : 'devolución', badge: rejection.rate === null ? 'N/A' : (rejection.rate > 0.3 ? 'Atención' : 'Óptimo'), tone: rejection.rate === null ? 'neutral' : (rejection.rate > 0.3 ? 'danger' : 'accent'), barColor: rejection.rate && rejection.rate > 0.3 ? '#9F2F2D' : '#346538', progressPercent: rejection.rate ? Math.round(rejection.rate * 100) : 0, tooltip: 'Relación de productos devueltos frente al total de productos tomados. Un valor alto sugiere problemas de precio, empaque o fecha de caducidad.' })}
      ${metricCard({ id: mid('dwell-time'), icono: 'timer', title: 'Permanencia Media', value: formatDwellTime(d.average_dwell_time_s), subtext: 'avg dwell', badge: 'Atención', tone: 'warning', highlight: true, barColor: '#B8790B', progressPercent: dwellProgress, tooltip: 'Tiempo promedio en segundos que las personas permanecieron frente al expositor durante su visita.' })}
    </div>
  </section>`;
}

function renderZonesSection(bundle = bundleDe(), idPrefix = '') {
  if (bundle.isLoadingMetrics) {
    return `
    <div class="bg-white rounded-xl border border-[#EAEAEA] p-5 space-y-3">
      <div class="h-4 skeleton rounded w-48"></div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div class="h-36 skeleton rounded-lg"></div>
        <div class="h-36 skeleton rounded-lg"></div>
      </div>
    </div>`;
  }
  if (bundle.errorMetrics) {
    return `
    <div class="bg-white rounded-xl border border-slate-200 p-6">
      <div class="p-4 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-sm">
        <p class="font-semibold mb-1">Métricas de zona no disponibles</p>
        <p class="text-xs text-amber-800">${esc(bundle.errorMetrics)}</p>
      </div>
    </div>`;
  }
  const zones = bundle.metrics;
  if (!zones || zones.length === 0) {
    return `
    <div class="bg-white rounded-xl border border-slate-200 p-8 text-center">
      ${icon('layers', 'w-8 h-8 text-slate-400 mx-auto mb-2')}
      <h3 class="text-sm font-semibold text-slate-700">No hay zonas configuradas en este video</h3>
      <p class="text-xs text-slate-500 mt-1">La API no devolvió registros de góndola o estante para esta grabación.</p>
    </div>`;
  }

  const isSingleZone = zones.length === 1;
  const viewMode = isSingleZone ? 'cards' : state.zonesViewMode; // preferencia compartida entre video principal y comparacion, a proposito: es solo un gusto de presentacion, no un dato distinto por video

  const viewToggle = isSingleZone ? '' : `
    <div class="inline-flex rounded-md border border-[#EAEAEA] p-0.5 bg-[#F3F2EF] self-start sm:self-auto">
      <button type="button" data-action="zones-view-table" class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded transition-colors ${viewMode === 'table' ? 'bg-white text-[#111111] shadow-xs font-semibold border border-[#EAEAEA]' : 'text-[#787774] hover:text-[#111111]'}">
        ${icon('table', 'w-3.5 h-3.5')}<span>Tabla</span>
      </button>
      <button type="button" data-action="zones-view-cards" class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded transition-colors ${viewMode === 'cards' ? 'bg-white text-[#111111] shadow-xs font-semibold border border-[#EAEAEA]' : 'text-[#787774] hover:text-[#111111]'}">
        ${icon('layout-grid', 'w-3.5 h-3.5')}<span>Tarjetas</span>
      </button>
    </div>`;

  const header = `
  <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white px-5 py-3.5 rounded-xl border border-[#EAEAEA] shadow-xs">
    <div class="flex items-center gap-3">
      <div class="w-7 h-7 bg-[#1F6C9F]/10 text-[#1F6C9F] rounded-lg flex items-center justify-center shrink-0">${icon('layers', 'w-4 h-4')}</div>
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-sm font-bold text-[#111111]">Análisis Detallado por Zona</h2>
          <span class="px-2 py-0.5 bg-[#FBF3DB] text-[#956400] text-[10px] font-bold rounded">${isSingleZone ? '1 ZONA' : `${zones.length} ZONAS`}</span>
          ${infoButton('Análisis Detallado por Zona', 'Cada fila es una zona calibrada a mano sobre el video (data/zones/), con las métricas que el pipeline calculó a partir de los eventos con esa zona asignada: cuántas personas entraron, cuántas interacciones/tomas/devoluciones hubo, y la permanencia promedio. Nada de esto es un estimado -son conteos directos de los eventos importados a PostgreSQL para este video.')}</div>
        <p class="text-[11px] text-[#787774]">${isSingleZone ? 'Monitoreo centrado en góndola principal' : 'Desglose y conversión por estante o nivel de planograma'}</p>
      </div>
    </div>
    ${viewToggle}
  </div>`;

  let body;
  if (viewMode === 'table') {
    const rows = zones.map((z) => {
      const intRate = z.interaction_rate !== null ? Math.round(z.interaction_rate * 100) : null;
      return `
      <tr class="hover:bg-[#F7F6F3] row-hover">
        <td class="px-5 py-3.5">
          <div class="font-medium text-[#111111]">${esc(z.name)}</div>
          <div class="text-[11px] text-[#A8A29E]">${z.level === 'gondola' ? 'Góndola' : z.level === 'shelf' ? 'Estante' : 'Zona'}</div>
        </td>
        <td class="px-4 py-3.5 text-xs">${z.product_category ? `<span class="font-medium text-[#2F3437]">${esc(z.product_category)}</span>` : `<span class="italic text-[#A8A29E]">sin datos</span>`}</td>
        <td class="px-4 py-3.5 text-center font-semibold text-[#111111]">${formatNumber(z.people_count)}</td>
        <td class="px-4 py-3.5 text-center">
          ${intRate !== null
            ? `<div class="flex items-center justify-center gap-2">
                 <div class="w-12 bg-[#F3F2EF] h-1.5 rounded-full overflow-hidden"><div class="bg-[#1F6C9F] h-full" style="width:${Math.min(100, intRate)}%"></div></div>
                 <span class="text-[11px] font-mono text-[#44403C]">${formatPercentage(z.interaction_rate)}</span>
               </div>`
            : `<span class="text-[11px] italic text-[#A8A29E]">sin datos</span>`}
        </td>
        <td class="px-4 py-3.5 text-center font-mono text-xs whitespace-nowrap">
          <span class="font-semibold text-[#2B5230]">${formatNumber(z.pick_up_count)}</span>
          <span class="text-[#D6D3D1] mx-1">/</span>
          <span class="font-semibold text-[#7F2523]">${formatNumber(z.put_back_count)}</span>
        </td>
        <td class="px-4 py-3.5 text-center text-xs font-mono text-[#787774]">${formatDwellTime(z.average_dwell_time_s)}</td>
        <td class="px-5 py-3.5 text-right font-semibold text-[#1F6C9F]">${z.conversion_rate !== null ? formatPercentage(z.conversion_rate) : '—'}</td>
      </tr>`;
    }).join('');

    body = `
    <div class="bg-white rounded-xl border border-[#EAEAEA] overflow-hidden shadow-xs">
      <div class="overflow-x-auto">
        <table class="text-left" style="width:100%;min-width:680px">
          <thead class="text-[10px] uppercase text-[#787774] tracking-wider border-b border-[#F3F2EF] bg-[#F9F9F8]">
            <tr>
              <th class="px-5 py-3 font-semibold whitespace-nowrap">Zona / Estantería</th>
              <th class="px-4 py-3 font-semibold whitespace-nowrap">Categoría</th>
              <th class="px-4 py-3 font-semibold text-center whitespace-nowrap">Personas</th>
              <th class="px-4 py-3 font-semibold text-center whitespace-nowrap">Interacción %</th>
              <th class="px-4 py-3 font-semibold text-center whitespace-nowrap">Tomas / Devol.</th>
              <th class="px-4 py-3 font-semibold text-center whitespace-nowrap">Permanencia</th>
              <th class="px-5 py-3 font-semibold text-right whitespace-nowrap">Conversión %</th>
            </tr>
          </thead>
          <tbody class="text-sm text-[#44403C] divide-y divide-[#F3F2EF]">${rows}</tbody>
        </table>
      </div>
    </div>`;
  } else {
    const cards = zones.map((z) => {
      const rejection = calculateRejectionRate(z.put_back_count, z.pick_up_count);
      return `
      <div id="zone-card-${esc(idPrefix)}${esc(z.zone_id)}" class="bg-white rounded-xl border border-[#EAEAEA] p-4 shadow-xs card-lift flex flex-col justify-between">
        <div>
          <div class="flex items-start justify-between gap-3 mb-2">
            <div>
              <div class="flex items-center gap-2">
                <span class="text-[10px] uppercase px-1.5 py-0.5 rounded bg-[#F3F2EF] text-[#57534E] font-bold border border-[#EAEAEA]">${z.level === 'gondola' ? 'Góndola' : z.level === 'shelf' ? 'Estante' : 'Zona'}</span>
                <h3 class="text-sm font-bold text-[#111111]">${esc(z.name)}</h3>
              </div>
            </div>
            <div class="text-right">
              ${z.product_category
                ? `<span class="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded bg-[#F7F6F3] border border-[#EAEAEA] text-[#44403C]">${icon('tag', 'w-3 h-3 text-[#A8A29E]')} ${esc(z.product_category)}</span>`
                : `<span class="text-[11px] italic text-[#A8A29E]">Sin categoría</span>`}
            </div>
          </div>
          <div class="grid grid-cols-4 gap-2 py-2.5 my-2 border-y border-[#F3F2EF]">
            <div class="p-2 rounded-lg bg-[#F7F6F3] border border-[#F3F2EF]"><div class="text-[10px] font-semibold text-[#787774] uppercase tracking-wider">Tráfico</div><div class="text-base font-bold text-[#111111]">${formatNumber(z.people_count)}</div></div>
            <div class="p-2 rounded-lg bg-[#F7F6F3] border border-[#F3F2EF]"><div class="text-[10px] font-semibold text-[#787774] uppercase tracking-wider">Int.</div><div class="text-base font-bold text-[#111111]">${formatNumber(z.interaction_count)}</div></div>
            <div class="p-2 rounded-lg bg-[#F7F6F3] border border-[#F3F2EF]"><div class="text-[10px] font-semibold text-[#787774] uppercase tracking-wider">Tomas</div><div class="text-base font-bold text-[#2B5230]">${formatNumber(z.pick_up_count)}</div></div>
            <div class="p-2 rounded-lg bg-[#F7F6F3] border border-[#F3F2EF]"><div class="text-[10px] font-semibold text-[#787774] uppercase tracking-wider">Devol.</div><div class="text-base font-bold text-[#7F2523]">${formatNumber(z.put_back_count)}</div></div>
          </div>
          <div class="grid grid-cols-3 gap-2 mt-2.5">
            <div class="p-2 rounded-lg border border-[#F3F2EF] bg-[#F9F9F8]"><div class="text-[10px] text-[#787774] uppercase tracking-wider font-semibold">Interacción</div><div class="text-sm font-bold text-[#111111]">${formatPercentage(z.interaction_rate)}</div></div>
            <div class="p-2 rounded-lg border border-[#F3F2EF] bg-[#F9F9F8]"><div class="text-[10px] text-[#787774] uppercase tracking-wider font-semibold">Toma / Int</div><div class="text-sm font-bold text-[#111111]">${formatPercentage(z.pick_up_rate)}</div></div>
            <div class="p-2 rounded-lg border border-[#F3F2EF] bg-[#F9F9F8]"><div class="text-[10px] text-[#787774] uppercase tracking-wider font-semibold">Conversión</div><div class="text-sm font-bold text-[#1F6C9F]">${formatPercentage(z.conversion_rate)}</div></div>
          </div>
        </div>
        <div class="mt-3 pt-2.5 border-t border-[#F3F2EF] flex flex-wrap items-center justify-between gap-2 text-xs text-[#787774]">
          <div class="flex items-center gap-1.5">${icon('clock', 'w-3 h-3 text-[#A8A29E]')}<span>Dwell: <strong class="text-[#111111]">${formatDwellTime(z.average_dwell_time_s)}</strong></span></div>
          <div class="flex items-center gap-1 text-[11px]"><span>Rechazo:</span><strong class="text-[#111111]">${rejection.label}</strong></div>
        </div>
      </div>`;
    }).join('');
    body = `<div class="grid gap-3.5 ${isSingleZone ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-2'}">${cards}</div>`;
  }

  return `<section aria-labelledby="zones-heading" class="space-y-3">${header}${body}</section>`;
}

// Mapa de calor de góndolas y estantes: cruza zoneHierarchy (estructura)
// con zoneMetrics (numeros) por zone_id, y colorea cada estante segun su
// people_count relativo al mas concurrido de ESTE video. Debajo dibuja un
// ranking horizontal de todas las zonas ordenadas por interaccion, para
// comparar de un vistazo cual estante gana y por cuanto.
// Mapa de calor REAL: densidad espacial continua sobre las coordenadas
// (x, y) crudas de GET /videos/{id}/positions (pies de cada persona
// detectada, en pixeles del frame original), no un agregado coloreado por
// zona -eso es renderZonesHeatmap(), mas abajo-. El div que devuelve esta
// funcion es solo el marco; heatmap.js dibuja adentro en initPositionsHeatmap(),
// llamado despues de cada render() porque necesita el nodo ya en el DOM
// con su tamano final (heatmap.js no sabe pintar sobre un string HTML).
function renderPositionsHeatmap(bundle = bundleDe()) {
  const current = state.videos.find((v) => v.video_id === bundle.videoId);
  if (bundle.isLoadingPositions) {
    return `
    <div class="bg-white rounded-xl border border-[#EAEAEA] p-5 shadow-xs">
      <div class="h-4 skeleton rounded w-56 mb-3"></div>
      <div class="h-64 skeleton rounded-lg"></div>
    </div>`;
  }
  if (!current || !bundle.positions.length) {
    return `
    <div class="bg-white rounded-xl border border-dashed border-[#D6D3D1] p-5 text-center text-xs text-[#787774]">
      Sin posiciones registradas todavía para este video.
    </div>`;
  }

  const aspect = current.width / current.height;
  return `
  <div class="rounded-xl border border-[#EAEAEA] p-5 shadow-xs" style="background:linear-gradient(165deg,#FFFFFF 0%,#EEF1F0 100%)">
    <div class="flex flex-wrap items-center justify-between gap-y-2 mb-1">
      <div class="flex items-center gap-2.5 min-w-0">
        <div class="w-7 h-7 rounded-lg bg-[#F3F2EF] text-[#787774] flex items-center justify-center shrink-0">${icon('compass', 'w-4 h-4')}</div>
        <div class="min-w-0">
          <h3 class="text-sm font-bold text-[#111111] inline-flex items-center gap-1.5">Mapa de Calor Real (por coordenadas) ${infoButton('Mapa de Calor Real', 'Cada punto es el punto de apoyo (los pies) de una persona detectada en un frame -la posición (x, y) en píxeles del video original, nunca su rostro ni identidad-. El mapa dibuja la densidad de TODOS esos puntos, cuadro a cuadro; no es un estimado ni un promedio, son las coordenadas reales que el pipeline registró.')}</h3>
          <p class="text-[11px] text-[#787774]">Densidad de ${formatNumber(bundle.positions.length)} posiciones detectadas, en píxeles del frame original</p>
        </div>
      </div>
      <div class="flex items-center gap-2.5 shrink-0 flex-wrap justify-end">
        <select id="heatmap-style-select" class="text-[11px] font-medium text-[#57534E] bg-[#F7F6F3] border border-[#EAEAEA] rounded-md px-1.5 py-1 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                title="Estilo visual del mapa de calor">
          ${Object.entries(HEATMAP_ESTILOS).map(([key, e]) => `<option value="${key}" ${state.heatmapStyle === key ? 'selected' : ''}>${esc(e.label)}</option>`).join('')}
        </select>
        <div class="flex items-center gap-1.5 text-[10px] text-[#787774] shrink-0 whitespace-nowrap">
          <span>Menos</span><div class="w-16 h-2 rounded shrink-0" style="background:${(HEATMAP_ESTILOS[state.heatmapStyle] || HEATMAP_ESTILOS.contraste).legendCss}"></div><span>Más</span>
        </div>
      </div>
    </div>
    <div class="relative mt-3 mx-auto" style="max-width:640px">
      <div id="${bundle.heatmapId}" data-frame-width="${current.width}" data-frame-height="${current.height}"
           class="relative w-full rounded-lg border border-[#EAEAEA] bg-[#0B1220] overflow-hidden"
           style="aspect-ratio:${aspect}">
      </div>
      <div class="flex justify-between text-[10px] font-mono text-[#A8A29E] mt-1 px-0.5">
        <span>x=0</span><span>x=${formatNumber(current.width)}px</span>
      </div>
    </div>
    <p class="text-[10px] text-[#A8A29E] text-center mt-1">Eje Y: 0px (arriba) a ${formatNumber(current.height)}px (abajo) — origen en la esquina superior izquierda del frame</p>
  </div>`;
}

// Estilos del mapa de calor: heatmap.js no solo pinta colores distintos
// con la opcion `gradient` (stop 0-1 -> color), tambien cambia de "sentir"
// segun el radio de cada punto y cuanto se difumina (`blur`). Cada estilo
// de aqui cambia las dos cosas a la vez -no solo repintar el mismo blob
// con otro color-, para que se note una diferencia real al cambiar:
//   - clasico: el de siempre (heatmap.js sin `gradient` propio).
//   - azul: un solo tono (el azul de marca), mas discreto.
//   - contraste: puntos mas chicos y sin difuminar casi nada -sirve para
//     ubicar el punto exacto de mayor concentracion, no la forma general-.
//   - suave: puntos grandes y muy difuminados -sirve para ver el patron
//     general de circulacion, no puntos exactos-.
// `legendCss` es el MISMO degradado, pero como string de CSS para pintar
// la barra "Menos -> Mas": tiene que coincidir con `gradient` a mano
// porque heatmap.js y `background: linear-gradient()` no comparten formato.
const HEATMAP_ESTILOS = {
  clasico: {
    label: 'Clásico',
    radiusFactor: 0.035, radiusMin: 16, blur: 0.85, maxOpacity: 0.9, minOpacity: 0,
    gradient: undefined, // heatmap.js sin `gradient` usa el suyo (azul->cian->verde->amarillo->rojo)
    legendCss: 'linear-gradient(90deg,#0B1220,#1F6C9F,#5AD1E0,#FFF06B,#E0472C)',
  },
  azul: {
    label: 'Monocromático',
    radiusFactor: 0.035, radiusMin: 16, blur: 0.85, maxOpacity: 0.85, minOpacity: 0,
    gradient: { 0.2: 'rgba(31,108,159,0.25)', 0.4: 'rgba(31,108,159,0.55)', 0.65: '#1F6C9F', 0.85: '#18567D', 1.0: '#0B3B5C' },
    legendCss: 'linear-gradient(90deg,rgba(31,108,159,0.2),#5CACD9,#1F6C9F,#0B3B5C)',
  },
  contraste: {
    label: 'Alto contraste',
    radiusFactor: 0.02, radiusMin: 9, blur: 0.35, maxOpacity: 1, minOpacity: 0.05,
    gradient: { 0.3: '#1F6C9F', 0.6: '#FFD400', 0.85: '#FF7A00', 1.0: '#E0472C' },
    legendCss: 'linear-gradient(90deg,#1F6C9F,#FFD400,#FF7A00,#E0472C)',
  },
  suave: {
    label: 'Difuminado',
    radiusFactor: 0.065, radiusMin: 30, blur: 0.97, maxOpacity: 0.7, minOpacity: 0,
    gradient: { 0.2: 'rgba(93,155,201,0.2)', 0.45: '#8FD3C9', 0.7: '#FFE08A', 1.0: '#F2A65A' },
    legendCss: 'linear-gradient(90deg,rgba(93,155,201,0.15),#8FD3C9,#FFE08A,#F2A65A)',
  },
};

// Ultimos datos pintados por contenedor, para saber si el mapa cambio de
// verdad o solo se volvio a renderizar la pantalla (ver el barrido de
// entrada mas abajo).
const HUELLA_MAPA = {};

// Pinta heatmap.js dentro de #<containerId>. Se llama despues de cada
// render() (ver app.js), nunca durante: heatmap.js necesita medir el
// contenedor ya insertado en el DOM (container.clientWidth) para saber a
// que escala de pixeles pintar. Recibe `positions` aparte (no state
// directamente) para poder pintar el mapa de CUALQUIER video -el
// principal o los de la comparacion-, cada uno en su propio contenedor.
function pintarHeatmap(containerId, positions) {
  const container = document.getElementById(containerId);
  if (!container || typeof h337 === 'undefined') return;
  const frameWidth = Number(container.dataset.frameWidth);
  const frameHeight = Number(container.dataset.frameHeight);
  if (!frameWidth || !frameHeight || !container.clientWidth) return;

  container.innerHTML = '';
  const estilo = HEATMAP_ESTILOS[state.heatmapStyle] || HEATMAP_ESTILOS.contraste;
  const configHeatmap = {
    container,
    radius: Math.max(estilo.radiusMin, Math.round(container.clientWidth * estilo.radiusFactor)),
    maxOpacity: estilo.maxOpacity,
    minOpacity: estilo.minOpacity,
    blur: estilo.blur,
  };
  if (estilo.gradient) configHeatmap.gradient = estilo.gradient;
  const heatmap = h337.create(configHeatmap);

  // heatmap.js pinta en pixeles de pantalla, no en pixeles del frame
  // original: hay que reescalar cada (x, y) a como se ve el contenedor
  // (que puede medir 640px de ancho para un frame de 1920px). Se agrupan
  // puntos que caen en el mismo pixel de pantalla (varios frames del mismo
  // track pasando por el mismo sitio) para que su "value" refleje
  // concentracion real, no un punto suelto por evento.
  const scaleX = container.clientWidth / frameWidth;
  const scaleY = container.clientHeight / frameHeight;
  const conteo = new Map();
  positions.forEach((p) => {
    const gx = Math.round(p.x * scaleX);
    const gy = Math.round(p.y * scaleY);
    const key = gx + ',' + gy;
    conteo.set(key, (conteo.get(key) || 0) + 1);
  });
  const data = Array.from(conteo, ([key, value]) => {
    const [x, y] = key.split(',').map(Number);
    return { x, y, value };
  });
  const max = Math.max(1, ...data.map((d) => d.value));
  heatmap.setData({ max, data });

  // Barrido de izquierda a derecha al pintar, con clip-path (no toca el
  // diseno, asi que el navegador lo resuelve sin recalcular nada). Se
  // dispara SOLO cuando cambian los datos de este contenedor, no en cada
  // render(): repetirlo al abrir un modal o cambiar de tema seria un
  // parpadeo constante encima del dato.
  const huella = positions.length + 'x' + data.length;
  if (HUELLA_MAPA[containerId] !== huella) {
    HUELLA_MAPA[containerId] = huella;
    container.classList.remove('revelar-mapa');
    void container.offsetWidth; // reinicia la animacion si ya estaba puesta
    container.classList.add('revelar-mapa');
  }

  // El mapa se pinta UNA vez, con los valores medidos, y se queda quieto.
  //
  // Antes habia aqui una animacion "viva" (parpadeo tipo brasa): un
  // setInterval cada 220ms que repintaba cada punto con
  // `value * (0.7 + Math.random() * 0.6)`. Se retiro, y no por gusto
  // visual: esa multiplicacion mostraba cada zona caliente con una
  // intensidad al azar entre el 70% y el 130% de su valor real, cuatro
  // veces por segundo. Quien miraba el mapa no estaba leyendo la
  // medicion, estaba leyendo ruido encima de la medicion -en un sistema
  // cuyo argumento entero es "medimos en vez de suponer", y delante de un
  // jurado que puede preguntar precisamente por ese mapa.
  //
  // De paso desaparecen dos efectos colaterales: un temporizador
  // permanente repintando un canvas entero mientras la pestana este
  // abierta, y el bloqueo que ese temporizador causaba en cualquier
  // herramienta que espere a que la pagina quede en reposo.
}

function renderZonesHeatmap(bundle = bundleDe()) {
  const zones = bundle.hierarchy;
  if (bundle.isLoadingHierarchy) {
    return `
    <div class="bg-white rounded-xl border border-[#EAEAEA] p-5 shadow-xs">
      <div class="h-4 skeleton rounded w-48 mb-3"></div>
      <div class="h-40 skeleton rounded-lg"></div>
    </div>`;
  }
  if (!zones || zones.length === 0) {
    return `
    <div class="bg-white rounded-xl border border-dashed border-[#D6D3D1] p-5 text-center text-xs text-[#787774]">
      Sin zonas configuradas todavía para este video.
    </div>`;
  }

  const metricsById = Object.fromEntries(bundle.metrics.map((m) => [m.zone_id, m]));
  const gondolas = zones.filter((z) => z.level === 'gondola');
  const shelvesByParent = {};
  zones.filter((z) => z.level === 'shelf').forEach((s) => {
    (shelvesByParent[s.parent_zone_id] ||= []).push(s);
  });

  const maxPeople = Math.max(1, ...zones.map((z) => (metricsById[z.zone_id] || {}).people_count || 0));
  const heatColor = (people) => {
    const t = Math.max(0, Math.min(1, people / maxPeople));
    const stops = t < 0.5
      ? [[214, 232, 245], [93, 155, 201], t / 0.5]
      : [[93, 155, 201], [11, 59, 92], (t - 0.5) / 0.5];
    const [a, b, local] = stops;
    const rgb = a.map((v, i) => Math.round(v + (b[i] - v) * local));
    return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
  };

  const shelfRow = (s) => {
    const m = metricsById[s.zone_id] || {};
    return `
    <div class="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 rounded px-3 py-2.5 mb-2 text-white text-xs" style="background:${heatColor(m.people_count || 0)}">
      <span class="font-semibold leading-snug">${esc(s.name)}</span>
      <span class="font-mono text-[11px] opacity-90 sm:ml-auto sm:text-right whitespace-nowrap">${formatNumber(m.people_count || 0)} pers · ${formatNumber(m.interaction_count || 0)} interac · ${formatDwellTime(m.average_dwell_time_s)}</span>
    </div>`;
  };

  const gondolaCard = (g) => {
    const m = metricsById[g.zone_id] || {};
    const shelves = shelvesByParent[g.zone_id] || [];
    const shelvesTotal = shelves.reduce((sum, s) => sum + ((metricsById[s.zone_id] || {}).people_count || 0), 0);
    const totalPeople = m.people_count || shelvesTotal;
    return `
    <div class="rounded-xl border border-[#EAEAEA] p-4 shadow-xs" style="background:linear-gradient(160deg,#FFFFFF 0%,#F3F2EF 100%)">
      <div class="flex items-baseline justify-between mb-3">
        <h4 class="text-sm font-bold text-[#111111]">${esc(g.name)}</h4>
        <span class="text-[11px] font-mono text-[#787774]">${formatNumber(totalPeople)} pers</span>
      </div>
      ${shelves.length ? shelves.map(shelfRow).join('') : `<div class="text-[11px] italic text-[#A8A29E]">Sin estantes configurados.</div>`}
    </div>`;
  };

  function renderRanking() {
    const compareList = zones.filter((z) => z.level === 'shelf').length
      ? zones.filter((z) => z.level === 'shelf')
      : zones;
    const withMetrics = compareList
      .map((z) => ({ ...z, m: metricsById[z.zone_id] || {} }))
      .sort((a, b) => (b.m.interaction_count || 0) - (a.m.interaction_count || 0));
    const maxInteraction = Math.max(1, ...withMetrics.map((z) => z.m.interaction_count || 0));

    const rows = withMetrics.map((z) => `
      <div class="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3">
        <span class="text-xs text-[#57534E] leading-snug sm:w-40 sm:shrink-0" title="${esc(z.name)}">${esc(z.name)}</span>
        <div class="flex-1 flex items-center gap-2">
          <div class="flex-1 bg-[#F3F2EF] h-3 rounded-full overflow-hidden">
            <div class="h-full rounded-full" style="width:${Math.max(4, Math.round((z.m.interaction_count || 0) / maxInteraction * 100))}%;background:#1F6C9F"></div>
          </div>
          <span class="text-xs font-mono text-[#111111] w-8 text-right shrink-0">${formatNumber(z.m.interaction_count || 0)}</span>
        </div>
      </div>`).join('');

    return `
    <div class="bg-white rounded-xl border border-[#EAEAEA] p-5 shadow-xs space-y-3">
      <div>
        <h3 class="text-sm font-bold text-[#111111]">Ranking de zonas por interacción</h3>
        <p class="text-[11px] text-[#787774]">Cuál estante genera más paradas de cliente, de mayor a menor</p>
      </div>
      <div class="space-y-2.5">${rows}</div>
    </div>`;
  }

  return `
  <div class="space-y-4">
    <div class="rounded-xl border border-[#EAEAEA] p-5 shadow-xs" style="background:linear-gradient(165deg,#FFFFFF 0%,#EEF1F0 100%)">
      <div class="flex flex-wrap items-center justify-between gap-y-2 mb-1">
        <div class="flex items-center gap-2.5 min-w-0">
          <div class="w-7 h-7 rounded-lg bg-[#F3F2EF] text-[#787774] flex items-center justify-center shrink-0">${icon('map', 'w-4 h-4')}</div>
          <div class="min-w-0">
            <h3 class="text-sm font-bold text-[#111111] inline-flex items-center gap-1.5">Resumen por Zona ${infoButton('Resumen por Zona', 'El color de cada estante sale de comparar su people_count contra el estante MÁS visitado del mismo video -no contra un umbral fijo-, así que "rojo" en un video con poco tráfico no significa lo mismo que "rojo" en uno con mucho. Los números (personas, interacciones, permanencia) vienen de la tabla metrics ya calculada por el pipeline, agregada por góndola y por estante.')}</h3>
            <p class="text-[11px] text-[#787774]">Total agregado por góndola/estante — el mapa de calor por coordenadas está arriba</p>
          </div>
        </div>
        <div class="flex items-center gap-1.5 text-[10px] text-[#787774] shrink-0 whitespace-nowrap">
          <span>Menos</span><div class="w-24 h-2 rounded shrink-0" style="background:linear-gradient(90deg,#D6E8F5,#5D9BC9,#0B3B5C)"></div><span>Más</span>
        </div>
      </div>
      <div class="grid gap-3.5 mt-3 ${gondolas.length > 1 ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1'}">${gondolas.map(gondolaCard).join('')}</div>
    </div>
    ${renderRanking()}
  </div>`;
}

// Umbral de muestra para el nivel de confianza de cada tarjeta: no es una
// cifra estadistica rigurosa (no hay margen de error calculado), es un piso
// practico -por debajo de 10 personas cualquier patron puede ser 2-3 casos
// sueltos, no una tendencia; de 30 en adelante ya pesa menos el ruido de
// una sola persona atipica.
const MUESTRA_CONFIANZA_BAJA = 10;
const MUESTRA_CONFIANZA_ALTA = 30;

function nivelConfianza(peopleCount) {
  const n = peopleCount || 0;
  if (n >= MUESTRA_CONFIANZA_ALTA) return 'alta';
  if (n >= MUESTRA_CONFIANZA_BAJA) return 'media';
  return 'baja';
}

// Diagnostico automatico ("Space Management en 10 segundos"): reglas
// simples sobre los numeros ya calculados (nada de IA ni llamada extra a la
// API) que arman 2-4 tarjetas de texto con una lectura y una accion
// sugerida. En el panel de un solo video vive en la columna DERECHA (ver
// app.js), debajo de "Privacidad y Ética"; en la comparacion se repite una
// vez por columna (ver renderVideoColumn(), vista-comparar.js), por eso
// toma un `bundle` igual que renderSummaryCards/renderZonesSection/etc.
//
// Cada tarjeta lleva un nivel de confianza (alta/media/baja) segun cuantas
// personas distintas sostienen el patron -el sistema mide comportamiento
// (se detienen, tocan, devuelven), nunca el producto en si (sin precio, sin
// empaque, sin reconocimiento visual de que es cada cosa), asi que el texto
// de "accion" solo puede pedir REVISAR en sitio, nunca nombrar una causa
// especifica que el sistema no tiene forma de ver.
function renderInsights(bundle = bundleDe()) {
  if (!bundle.detail) return '';
  const d = bundle.detail;
  const zones = bundle.metrics;
  const engagementRatio = d.people_count > 0 ? d.interaction_count / d.people_count : 0;
  const hasPickUps = d.pick_up_count > 0;
  const rejectionRatio = hasPickUps ? d.put_back_count / d.pick_up_count : 0;
  const dwell = d.average_dwell_time_s || 0;
  const confianzaVideo = nivelConfianza(d.people_count);

  const list = [];
  if (d.people_count === 0) {
    list.push({ type: 'neutral', confianza: confianzaVideo, title: 'Sin tránsito en el pasillo', desc: 'No se detectaron personas durante este periodo de grabación.', action: 'Evaluar iluminación de cabecera o señalética direccional de pasillo.' });
  } else if (engagementRatio >= 0.8) {
    list.push({ type: 'success', confianza: confianzaVideo, title: 'Alta atracción de clientes al expositor', desc: `Un promedio de ${engagementRatio.toFixed(1)} interacciones por transeúnte con permanencia media de ${formatDwellTime(dwell)}.`, action: 'Mantener la posición de categoría; los clientes se detienen con naturalidad frente a este espacio.' });
  } else if (engagementRatio < 0.4) {
    list.push({ type: 'attention', confianza: confianzaVideo, title: 'Tráfico de paso rápido (Baja detención)', desc: 'La mayoría de personas circulan frente a la góndola sin detenerse ni interactuar.', action: 'Considerar productos gancho o cartelería promocional a la altura de los ojos (1.40m - 1.60m) para frenar el paso.' });
  }
  if (hasPickUps) {
    if (rejectionRatio > 0.4) {
      list.push({ type: 'attention', confianza: confianzaVideo, title: `Fricción de compra: ${Math.round(rejectionRatio * 100)}% de tomas devueltas`, desc: `De ${d.pick_up_count} tomas registradas, ${d.put_back_count} fueron devueltas a la góndola sin compra.`, action: 'Revisar el estante en sitio: el sistema detecta el patrón de devolución, pero no analiza el producto, así que no puede decir si la causa es precio, empaque o algo distinto.' });
    } else if (d.put_back_count === 0) {
      list.push({ type: 'success', confianza: confianzaVideo, title: 'Decisión directa: 0% devoluciones', desc: `Todas las ${d.pick_up_count} tomas de producto se mantuvieron en poder del cliente.`, action: 'Planograma óptimo: la presentación del producto genera convicción inmediata en el comprador.' });
    }
  } else if (d.interaction_count > 5 && d.pick_up_count === 0) {
    list.push({ type: 'attention', confianza: confianzaVideo, title: 'Interacción visual sin contacto físico', desc: 'Los clientes se detienen frente a la góndola pero no toman ningún artículo con las manos.', action: 'Revisar accesibilidad física del estante y visibilidad frontal del surtido.' });
  }
  if (zones.length > 1) {
    const bestZone = [...zones].sort((a, b) => (b.conversion_rate || 0) - (a.conversion_rate || 0))[0];
    if (bestZone && (bestZone.conversion_rate || 0) > 0) {
      list.push({ type: 'success', confianza: nivelConfianza(bestZone.people_count), title: `Zona líder en conversión: ${bestZone.name}`, desc: `Registró la mayor tasa de conversión (${formatPercentage(bestZone.conversion_rate)}) entre los estantes analizados.`, action: `Aprovechar el nivel '${bestZone.level}' para productos de mayor margen comercial o lanzamientos.` });
    }
  }

  const CLASE_CONFIANZA = {
    alta: 'bg-[#EDF3EC] text-[#346538]',
    media: 'bg-[#FBF3DB] text-[#956400]',
    baja: 'bg-[#FAE4E4] text-[#9F2F2D]',
  };
  const cards = list.map((rec) => {
    const isSuccess = rec.type === 'success';
    const isAttention = rec.type === 'attention';
    const cls = isSuccess ? 'bg-[#EDF3EC]/60 border-[#C7D6C5] text-[#346538]' : isAttention ? 'bg-[#FBF3DB]/40 border-[#EDD9A3] text-[#956400]' : 'bg-[#F7F6F3] border-[#EAEAEA] text-[#2F3437]';
    const iconHtml = isSuccess ? icon('check-circle-2', 'w-3.5 h-3.5 text-[#2B5230] shrink-0') : isAttention ? icon('alert-circle', 'w-3.5 h-3.5 text-[#956400] shrink-0') : icon('lightbulb', 'w-3.5 h-3.5 text-[#787774] shrink-0');
    const confianzaHtml = rec.confianza ? `<span class="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${CLASE_CONFIANZA[rec.confianza]}" title="Nivel de confianza segun cuantas personas distintas sostienen este patron">Confianza ${esc(rec.confianza)}</span>` : '';
    return `
    <div class="rounded-lg p-3 border flex flex-col justify-between ${cls}">
      <div>
        <div class="flex items-center gap-1.5 mb-1.5 flex-wrap">${iconHtml}<h4 class="text-xs font-bold leading-tight text-[#111111]">${esc(rec.title)}</h4>${confianzaHtml}</div>
        <p class="text-[11px] text-[#57534E] leading-relaxed mb-2.5">${esc(rec.desc)}</p>
      </div>
      <div class="pt-2 border-t border-black/5 flex items-start gap-1.5 text-[11px]">
        ${icon('arrow-right', 'w-3 h-3 text-[#1F6C9F] shrink-0 mt-0.5')}
        <span class="text-[#44403C]"><strong class="text-[#111111]">Acción:</strong> ${esc(rec.action)}</span>
      </div>
    </div>`;
  }).join('');

  return `
  <div class="bg-white rounded-xl border border-[#EAEAEA] p-4.5 shadow-xs space-y-3.5">
    <div class="flex flex-col gap-2.5 border-b border-[#F3F2EF] pb-3">
      <div class="flex items-center gap-2.5">
        <div class="w-7 h-7 rounded-lg bg-[#1F6C9F]/10 text-[#1F6C9F] flex items-center justify-center shrink-0">${icon('compass', 'w-4 h-4')}</div>
        <div>
          <h3 class="text-sm font-bold text-[#111111] inline-flex items-center gap-1.5">Diagnóstico de Space Management en 10 Segundos ${infoButton('Diagnóstico de Space Management', 'Cada tarjeta sale de reglas simples sobre los números que ya calculó el pipeline (personas distintas, interacciones, tomas, devoluciones, permanencia) -no hay un modelo de IA nuevo, solo comparaciones entre esos datos-. El nivel de confianza (alta/media/baja) depende de cuántas personas distintas sostienen el patrón: con menos de 10 puede ser ruido, no tendencia. El sistema mide comportamiento, nunca analiza el producto en sí.')}</h3>
          <p class="text-[11px] text-[#787774]">Síntesis ejecutiva de comportamiento para gerencia de tienda y planogramación</p>
        </div>
      </div>
      <div class="self-start inline-flex items-center gap-1.5 text-[11px] text-[#787774] bg-[#F7F6F3] px-2.5 py-1 rounded-md border border-[#EAEAEA]">
        ${icon('trending-up', 'w-3.5 h-3.5 text-[#1F6C9F]')}<span>Telemetría de video anónima</span>
      </div>
    </div>
    <div class="grid grid-cols-1 gap-3">${cards}</div>
  </div>`;
}

function renderSidebar() {
  let rejectionRate = '0.0';
  let rejectionDesc = 'No se han registrado devoluciones a estantería tras toma de producto en este intervalo.';
  if (state.videoDetail && state.videoDetail.total_pick_ups !== 0) {
    const d = state.videoDetail;
    if (d.pick_up_count > 0) {
      const rate = (d.put_back_count / d.pick_up_count) * 100;
      rejectionRate = rate.toFixed(1);
      rejectionDesc = d.put_back_count === 0
        ? 'Retención óptima: 100% de los productos tomados fueron conservados sin devoluciones a góndola.'
        : `${d.put_back_count} de ${d.pick_up_count} productos tomados fueron devueltos a la estantería.`;
    }
  }

  return `
  <div class="bg-[#2A2E31] text-white p-5 rounded-xl relative overflow-hidden shadow-xs border border-[#3A3F42]">
    <div class="relative z-10">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-xs font-bold uppercase tracking-widest text-[#A8A29E] inline-flex items-center gap-1.5">Tasa de Rechazo Global ${infoButton('Tasa de Rechazo Global', 'put_back_count ÷ pick_up_count de todo el video, en porcentaje. Sin ninguna toma detectada (pick_up_count = 0) esta tarjeta muestra 0.0% por defecto, pero eso NO es lo mismo que "0% de rechazo real": es un dato ausente, no una tasa calculada -ver la tarjeta de Retroalimentación para esa aclaración con los números concretos de este video.')}</h3>
        <span class="text-[10px] font-mono text-[#A8A29E] px-1.5 py-0.5 rounded bg-white/10">PUT-BACKS</span>
      </div>
      <div class="text-3xl sm:text-4xl font-bold mb-2 tracking-tight text-[#E5E3DE]">${rejectionRate}<span class="text-lg opacity-50 font-normal">%</span></div>
      <p class="text-xs text-[#A8A29E] leading-relaxed">${esc(rejectionDesc)}</p>
    </div>
  </div>

  <div class="bg-white p-5 rounded-xl border border-[#EAEAEA] shadow-xs space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-xs font-bold uppercase tracking-widest text-[#787774]">Privacidad y Ética</h3>
      <span class="px-1.5 py-0.5 bg-[#EDF3EC] text-[#346538] text-[9px] font-bold rounded">ANÓNIMO</span>
    </div>
    <div class="space-y-3.5">
      <div class="flex gap-3">
        <div class="shrink-0 w-7 h-7 rounded-full bg-[#EDF3EC] flex items-center justify-center text-[#346538]">${icon('check', 'w-3.5 h-3.5')}</div>
        <p class="text-xs text-[#57534E]"><strong class="text-[#2F3437] block mb-0.5">Anonimato Total</strong>Las trayectorias se vinculan a IDs temporales y efímeros.</p>
      </div>
      <div class="flex gap-3">
        <div class="shrink-0 w-7 h-7 rounded-full bg-[#EDF3EC] flex items-center justify-center text-[#346538]">${icon('check', 'w-3.5 h-3.5')}</div>
        <p class="text-xs text-[#57534E]"><strong class="text-[#2F3437] block mb-0.5">Sin Datos PII</strong>No se procesan rostros, edades, ni identidades personales.</p>
      </div>
    </div>
  </div>`;
}

function errorAlert({ title, detail, retryAction, showMock = true, isRetrying = false }) {
  return `
  <div class="bg-white rounded-xl border border-red-200 p-6 shadow-xs my-4 space-y-4">
    <div class="flex items-start gap-3">
      <div class="p-2 rounded-lg bg-red-50 text-red-600 shrink-0">${icon('alert-circle', 'w-6 h-6')}</div>
      <div class="flex-1">
        <h3 class="text-base font-bold text-slate-900">${esc(title)}</h3>
        <div class="mt-1 p-3 rounded-lg bg-red-50/70 border border-red-100 font-mono text-xs text-red-900 leading-relaxed">${esc(detail)}</div>
        <p class="text-xs text-slate-500 mt-2">El backend FastAPI no devolvió los datos esperados o la conexión no pudo establecerse.</p>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
      <button type="button" data-action="${retryAction}" ${isRetrying ? 'disabled' : ''} class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-xs disabled:opacity-50 transition-colors">
        ${icon('refresh-cw', `w-3.5 h-3.5 ${isRetrying ? 'animate-spin' : ''}`)} Reintentar petición
      </button>
      ${showMock ? `<button type="button" data-action="enable-mock" class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 text-xs font-semibold transition-colors">${icon('database', 'w-3.5 h-3.5')} Explorar con Datos de Demostración del Contrato</button>` : ''}
      <button type="button" data-action="open-settings" class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium transition-colors">${icon('sliders', 'w-3.5 h-3.5')} Configurar URL del Backend</button>
    </div>
  </div>`;
}
