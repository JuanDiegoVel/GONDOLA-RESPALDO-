// Vista de comparacion entre dos videos
// Parte del dashboard de Gondola Inteligente. Se carga desde index.html
// como <script> clasico (no modulo ES): ver el comentario de index.html.

// `seccionId` solo llega con valor desde la pestana 'reportes' del panel
// principal (app.js); dentro de comparar (que no tiene pestanas) se llama
// sin el, y cae al hasAnimatedIn de siempre -una sola vez por sesion-.
function renderFeedback(bundle = bundleDe(), seccionId = null) {
  const notas = generarNotasFeedback(bundle);
  if (!notas.length) return '';
  const entra = seccionId ? debeAnimarSeccion(seccionId) : !hasAnimatedIn;

  const items = notas.slice(0, 4).map((n) => `
    <div class="flex gap-2.5">
      <div class="w-5 h-5 rounded-full bg-[#F3F2EF] text-[#787774] flex items-center justify-center shrink-0 mt-0.5">${icon('help-circle', 'w-3 h-3')}</div>
      <div>
        <p class="text-xs font-bold text-[#111111] leading-snug">${esc(n.titulo)}</p>
        <p class="text-[11px] text-[#57534E] leading-relaxed mt-0.5">${esc(n.texto)}</p>
      </div>
    </div>`).join('');

  return `
  <div class="bg-white rounded-xl border border-[#EAEAEA] p-4 sm:p-5 shadow-xs">
    <div class="flex items-center gap-2.5 mb-3">
      <div class="w-7 h-7 rounded-lg bg-[#FBF3DB] text-[#956400] flex items-center justify-center shrink-0">${icon('help-circle', 'w-4 h-4')}</div>
      <div>
        <h3 class="text-sm font-bold text-[#111111] inline-flex items-center gap-1.5">Retroalimentación: por qué salen estos números ${infoButton('Retroalimentación automática', 'Son reglas simples (sin IA) que revisan los números ya calculados de este video -pick_up_count, put_back_count, duration_s, people_count- y señalan cuándo un número puede tener una explicación distinta a la obvia: un video corto, un dataset pensado para una sola persona, un umbral de detección al límite, etc. El objetivo es que no se lea un porcentaje como una verdad absoluta sin conocer sus límites.')}</h3>
        <p class="text-[11px] text-[#787774]">Para entender el resultado sin tener que ver el video completo</p>
      </div>
    </div>
    <div class="${entra ? 'stagger-in' : ''} space-y-3">${items}</div>
  </div>`;
}

// Los mismos 4 numeros de dos videos, uno al lado del otro. Pura
// presentacion: no hace ninguna cuenta nueva, solo reutiliza los resumenes
// que ya trajo loadCompareData() para cada lado.
function renderCompareNumbers(a, b) {
  const rejA = calculateRejectionRate(a.put_back_count, a.pick_up_count);
  const rejB = calculateRejectionRate(b.put_back_count, b.pick_up_count);

  const compareRow = (label, va, vb, fmt = formatNumber) => `
    <div class="grid grid-cols-3 items-center gap-2 py-2.5 border-b border-[#F3F2EF] last:border-0">
      <div class="text-sm font-bold text-[#111111] text-right tabular-nums">${fmt(va)}</div>
      <div class="text-[10px] text-[#787774] uppercase tracking-wider text-center">${esc(label)}</div>
      <div class="text-sm font-bold text-[#111111] tabular-nums">${fmt(vb)}</div>
    </div>`;

  return `
  <div class="bg-white rounded-xl border border-[#EAEAEA] p-5 shadow-xs space-y-1">
    <div class="grid grid-cols-3 items-center text-center pb-2 border-b border-[#EAEAEA]">
      <div class="text-xs font-semibold text-[#1F6C9F] truncate" title="${esc(a.source_name || a.video_id)}">${esc(a.source_name || a.video_id)}</div>
      <div class="text-[10px] text-[#A8A29E] font-bold">VS</div>
      <div class="text-xs font-semibold text-[#1F6C9F] truncate" title="${esc(b.source_name || b.video_id)}">${esc(b.source_name || b.video_id)}</div>
    </div>
    ${compareRow('Personas', a.people_count, b.people_count)}
    ${compareRow('Interacciones', a.interaction_count, b.interaction_count)}
    ${compareRow('Permanencia', a.average_dwell_time_s, b.average_dwell_time_s, formatDwellTime)}
    ${compareRow('Tasa de rechazo', rejA.rate !== null ? Math.round(rejA.rate * 100) + '%' : '—', rejB.rate !== null ? Math.round(rejB.rate * 100) + '%' : '—', (v) => v)}
  </div>`;
}

// Una columna COMPLETA para un video de la comparacion: mismo contenido
// que ve alguien mirando un solo video (video, resumen, zonas, mapa de
// calor, resumen de zona, diagnostico de space management,
// retroalimentacion) -antes esta vista solo traia 4 numeros sueltos, y eso
// no alcanzaba para comparar de verdad dos videos-. Reutiliza exactamente
// las mismas funciones de render que el panel principal, pasandoles el
// bundle de este slot en vez del video principal.
function renderVideoColumn(slot) {
  const bundle = bundleDe(slot);
  const videoId = bundle.videoId;
  if (!videoId) {
    return `
    <div class="bg-white rounded-xl border border-dashed border-[#D6D3D1] p-8 text-center text-xs text-[#787774]" style="min-height:220px">
      Elige el video ${slot} arriba para ver su análisis completo
    </div>`;
  }

  const current = state.videos.find((v) => v.video_id === videoId);
  const demo = isDemoVideo(videoId);
  const placeholderId = `video-compare-${slot.toLowerCase()}-placeholder`;
  const idPrefix = slot.toLowerCase();

  const videoCard = demo
    ? `<div class="bg-white rounded-xl border border-[#EAEAEA] p-5 flex items-center justify-center text-center text-xs text-[#787774]" style="min-height:220px">Video de prueba: sin grabación real que mostrar</div>`
    : `<div class="bg-white rounded-xl border border-[#EAEAEA] p-3 shadow-xs"><div id="${placeholderId}" class="w-full rounded-lg bg-[#0B1220]" style="height:220px"></div></div>`;

  return `
  <div class="space-y-4">
    <div class="flex items-center gap-2 pb-1">
      <span class="w-6 h-6 rounded-full bg-[#1F6C9F] text-white text-xs font-bold flex items-center justify-center shrink-0">${slot}</span>
      <h3 class="text-sm font-bold text-[#111111] truncate" title="${esc(current ? current.source_name : videoId)}">${esc(current ? current.source_name : videoId)}</h3>
      <span class="text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 ${demo ? 'bg-[#FBF3DB] text-[#956400]' : 'bg-[#EDF3EC] text-[#346538]'}">${demo ? 'PRUEBA' : 'REAL'}</span>
    </div>
    ${videoCard}
    ${renderSummaryCards(bundle, idPrefix)}
    ${renderZonesSection(bundle, `${idPrefix}-`)}
    ${renderPositionsHeatmap(bundle)}
    ${renderZonesHeatmap(bundle)}
    ${renderInsights(bundle)}
    ${renderFeedback(bundle)}
  </div>`;
}

// Apartado APARTE de la pantalla principal (ver "mostrandoComparacion" en
// state y el boton "Comparar dos videos" en renderVideoSelector): dos
// selectores arriba, un digest rapido de 4 numeros, y debajo las DOS
// columnas completas (renderVideoColumn) una al lado de la otra. Vivir
// separado del panel de un solo video es lo que evita el bug de
// reproductor en blanco que habia antes (ver el comentario junto a
// "mostrandoComparacion" en estado.js), y tiene su PROPIA ruta en el hash
// (#/comparar, ver 'abrir-comparacion'/'cerrar-comparacion' en app.js) para
// que el boton ATRAS del navegador vuelva al video unico, no a la portada.
function renderComparisonView() {
  // El video ya elegido en el OTRO slot no aparece en esta lista: comparar
  // un video contra si mismo no tiene sentido (todas las cifras saldrian
  // identicas, y confundiria mas que ayudaria).
  const selector = (slot, valorActual, idDelOtroLado) => `
    <div class="flex items-center gap-2 px-3 py-1.5 bg-[#F3F2EF] rounded-md border border-[#EAEAEA] flex-1 min-w-[220px]">
      <span class="text-xs font-medium text-[#57534E] uppercase tracking-wider shrink-0">Video ${slot}:</span>
      <select data-compare-slot="${slot}" class="bg-transparent text-sm font-semibold text-[#2F3437] outline-none cursor-pointer w-full py-0.5">
        <option value="">Elegir…</option>
        ${state.videos.filter((v) => v.video_id !== idDelOtroLado).map((v) => `<option value="${esc(v.video_id)}" ${v.video_id === valorActual ? 'selected' : ''}>${esc(v.source_name || v.video_id)} ${isDemoVideo(v.video_id) ? '(Prueba)' : '(Real)'}</option>`).join('')}
      </select>
    </div>`;

  const numeros = (!state.compareADetail || !state.compareBDetail)
    ? (state.isLoadingCompareA || state.isLoadingCompareB
        ? `<div class="bg-white rounded-xl border border-[#EAEAEA] p-5 shadow-xs"><div class="h-4 skeleton rounded w-48 mb-3"></div><div class="h-20 skeleton rounded-lg"></div></div>`
        : `<div class="bg-white rounded-xl border border-dashed border-[#D6D3D1] p-5 text-center text-xs text-[#787774]">Elige los dos videos para ver la comparación completa.</div>`)
    : renderCompareNumbers(state.compareADetail, state.compareBDetail);

  return `
  <main class="flex-1 max-w-[1600px] w-full mx-auto px-4 sm:px-6 py-5 space-y-4">
    <button type="button" data-action="cerrar-comparacion"
            class="inline-flex items-center gap-1.5 text-sm font-medium text-[#1F6C9F] hover:text-[#18567D] transition-colors">
      ${icon('arrow-left', 'w-4 h-4')} Volver al panel principal
    </button>
    <div class="bg-white rounded-xl border border-[#EAEAEA] p-4 shadow-xs">
      <h2 class="text-sm font-bold text-[#111111] mb-3">Comparar dos videos</h2>
      <div class="flex flex-col sm:flex-row gap-3">
        ${selector('A', state.compareA, state.compareB)}
        ${selector('B', state.compareB, state.compareA)}
      </div>
    </div>
    ${numeros}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      ${renderVideoColumn('A')}
      ${renderVideoColumn('B')}
    </div>
  </main>`;
}
