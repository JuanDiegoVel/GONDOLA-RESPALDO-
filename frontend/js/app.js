// render(), eventos y arranque
// Parte del dashboard de Gondola Inteligente. Se carga desde index.html
// como <script> clasico (no modulo ES): ver el comentario de index.html.

// Ultimo video cuyos numeros se animaron, para no repetir la animacion.
let hasAnimatedIn = false;
let lastCountedVideoId = null;

// Que apartados del panel (resumen/zonas/mapa/reportes, ver SECCIONES_PANEL
// en vista-panel.js) ya mostraron su entrada escalonada al menos una vez.
// hasAnimatedIn de arriba solo cubre el <main> entero en el primer render de
// la sesion -y con el panel repartido en pestanas, esa primera vez casi
// siempre te encuentra parado en 'resumen': las demas pestanas nunca llegan
// a VERSE en ese instante (estan en display:none), asi que su animacion
// pasaba de largo sin que nadie la viera. Aqui se guarda, por separado, la
// primera vez que CADA pestana se vuelve la activa -asi entra escalonada
// la primera vez que entras a 'zonas', y otra vez la primera vez que entras
// a 'mapa', aunque sea en la misma sesion-. Igual que hasAnimatedIn, cambiar
// de video NO la repite (ver el comentario de firstPaint mas abajo): eso lo
// comunican el conteo de las cifras y el crecimiento de las barras.
const seccionesAnimadas = new Set();
function debeAnimarSeccion(id) {
  return !seccionesAnimadas.has(id) && !!state.videoDetail;
}

function render() {
  const root = document.getElementById('root');
  // La clase vive en <html>, no en #root: #root se reconstruye entero en
  // cada render() (ver el comentario grande junto a #root en index.html),
  // pero el CSS de modo oscuro esta escrito contra "html.dark ..." para
  // que siga aplicando aunque #root cambie de contenido -incluida la
  // pantalla de bienvenida-.
  document.documentElement.classList.toggle('dark', state.darkMode);

  if (state.mostrandoInicio) {
    // Antes del return: la portada no tiene hueco para el reproductor, y
    // como vive fuera de #root (ver reproductor.js) nadie mas lo iba a
    // esconder -bug real, encontrado en la practica: el boton ATRAS del
    // navegador podia traer de vuelta la portada mientras un video seguia
    // reproduciendose en el panel o en la comparacion, y se quedaba
    // flotando encima, todavia sonando.
    ocultarReproductores();
    root.innerHTML = renderPantallaInicio();
    return;
  }

  const errorBlocks = [
    state.errorVideos ? errorAlert({ title: 'Error al consultar lista de videos (/videos)', detail: state.errorVideos, retryAction: 'refresh-videos', isRetrying: state.isLoadingVideos }) : '',
    state.errorDetail ? errorAlert({ title: `Error al consultar video ${esc(state.selectedVideoId)} (/videos/${esc(state.selectedVideoId)})`, detail: state.errorDetail, retryAction: 'retry-detail', isRetrying: state.isLoadingDetail }) : '',
  ].join('');

  // Entrada escalonada, SOLO la primera vez que llegan datos en la sesion
  // (hasAnimatedIn se queda en true despues). Cambiar de video no la
  // repite: ahi el movimiento que comunica algo es el conteo de las cifras
  // y el crecimiento de las barras (ver fillCountUps() y .kpi-bar). Los
  // escalones son cortos -el ultimo no llega a 200ms- para que se sienta
  // que la pantalla se arma, no que hay que esperarla.
  const firstPaint = !hasAnimatedIn && !!state.videoDetail;

  // Sin video elegido -a proposito no se auto-elige ninguno, ver
  // loadVideos()-, no tiene sentido mostrar tarjetas de zonas/mapa de
  // calor/etc. todas vacias: se corta ahi con un solo mensaje central.
  const sinVideoElegido = !state.selectedVideoId && !state.isLoadingVideos;

  // El panel se reparte en secciones (ver SECCIONES_PANEL y seccionPanel(),
  // en vista-panel.js) en vez de apilarlo todo en un solo scroll. Se pintan
  // TODAS y se oculta la que no esta activa: asi el reporte en PDF sigue
  // saliendo completo y el hueco del reproductor de video sigue existiendo
  // para que su portal pueda medirlo. Ver .panel-seccion en estilos.css.
  const secciones = `
      ${seccionPanel('resumen', `
        ${renderSummaryCards()}
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start mt-4">
          <div class="lg:col-span-7">${renderInsights()}</div>
          <div class="lg:col-span-5 space-y-4">${renderSidebar()}</div>
        </div>`)}
      ${seccionPanel('zonas', `
        <div class="space-y-4">
          ${renderZonesSection()}
          ${renderZonesHeatmap()}
        </div>`)}
      ${seccionPanel('mapa', renderPositionsHeatmap())}
      ${seccionPanel('video', renderVideoPlayer() || `
        <div class="bg-white rounded-xl border border-dashed border-[#D6D3D1] py-16 text-center">
          ${icon('video-camera', 'w-8 h-8 text-[#A8A29E] mx-auto mb-3')}
          <h3 class="text-sm font-semibold text-[#2F3437]">Este video no tiene render anonimizado</h3>
          <p class="text-xs text-[#787774] mt-1 max-w-md mx-auto">Los videos de prueba no tienen ninguna grabación detrás. En un video real aparece aquí el render en modo privacidad, sin un solo píxel del original.</p>
        </div>`)}
      ${seccionPanel('reportes', renderFeedback(undefined, 'reportes') || `
        <div class="bg-white rounded-xl border border-dashed border-[#D6D3D1] py-16 text-center">
          ${icon('check-circle-2', 'w-8 h-8 text-[#346538] mx-auto mb-3')}
          <h3 class="text-sm font-semibold text-[#2F3437]">Sin advertencias para este video</h3>
          <p class="text-xs text-[#787774] mt-1 max-w-md mx-auto">Aquí aparecen los avisos sobre cómo leer los números — un video demasiado corto, cero tomas detectadas, un porcentaje sin denominador. Este video no dispara ninguno.</p>
        </div>`)}`;

  const mainContent = state.mostrandoComparacion
    ? renderComparisonView()
    : `
    <div class="flex-1 w-full max-w-[1600px] mx-auto px-4 sm:px-6 py-5 flex flex-col lg:flex-row gap-4 lg:gap-5 items-start">
      ${sinVideoElegido ? '' : renderNavSecciones()}
      <main class="flex-1 min-w-0 w-full space-y-4 ${firstPaint ? 'stagger-in' : ''}">
        ${renderVideoSelector()}
        ${errorBlocks}
        ${sinVideoElegido ? `
        <div class="bg-white rounded-xl border border-dashed border-[#D6D3D1] py-16 text-center">
          ${icon('layers', 'w-8 h-8 text-[#A8A29E] mx-auto mb-3')}
          <h3 class="text-sm font-semibold text-[#2F3437]">Elige un video arriba para ver su análisis</h3>
          <p class="text-xs text-[#787774] mt-1">El panel no elige uno por ti — selecciona uno del desplegable "Video".</p>
        </div>` : secciones}
      </main>
    </div>`;

  root.innerHTML = `
    <div class="no-imprimir">${renderHeader()}</div>
    <div class="no-imprimir">${renderConnectionBanner()}</div>
    ${mainContent}
    ${renderConfigModal()}
    ${renderSubidaModal()}
    ${renderInfoModal()}
  `;

  if (firstPaint) hasAnimatedIn = true;
  // No se marca AQUI mismo, de forma sincrona: al elegir un video, el
  // detalle/metricas/zonas/posiciones llegan de fetch() separados que en
  // localhost pueden resolver a milisegundos uno del otro, y cada uno
  // dispara su propio render(). Si el primero marcaba la seccion al
  // toque, el SEGUNDO (llegando antes de que el navegador pintara el
  // primero) ya salia sin stagger-in: el cascade nunca llegaba a
  // pintarse, solo el resultado ya asentado -bug real, visto con un
  // MutationObserver, es la razon de que "saliera todo de golpe" pese a
  // que la clase si se ponia-. Esperar dos frames de animacion antes de
  // marcar le da tiempo al navegador a pintar con la clase puesta al
  // menos una vez; cualquier render que llegue mientras tanto la sigue
  // trayendo tambien, asi que no se pierde nada.
  if (state.videoDetail) {
    const seccion = state.panelSeccion;
    requestAnimationFrame(() => requestAnimationFrame(() => seccionesAnimadas.add(seccion)));
  }
  fillCountUps();

  // Tailwind (CDN) inyecta el CSS de las clases nuevas de forma asincrona
  // -no esta listo en el mismo tick en que se reemplaza root.innerHTML-,
  // asi que medir posiciones (getBoundingClientRect, container.clientWidth)
  // justo aqui puede leer un layout todavia sin estilos aplicados: el
  // reproductor de video quedaba flotando en un sitio equivocado (bug
  // real, visto en pantalla) porque se posicionaba contra ese layout a
  // medias. Un doble requestAnimationFrame espera a que el navegador ya
  // haya pintado con los estilos puestos antes de medir nada.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (state.mostrandoComparacion) {
      pintarMapaAunqueOculto('positions-heatmap-canvas-a', state.compareAPositions);
      pintarMapaAunqueOculto('positions-heatmap-canvas-b', state.compareBPositions);
    } else {
      pintarMapaAunqueOculto('positions-heatmap-canvas', state.positions);
    }
    initVideoPlayer();
    initLienzoZonas();
  }));
}

// El mapa de calor lo pinta heatmap.js sobre un <canvas>, y pintarHeatmap()
// se planta si el contenedor mide 0 de ancho (guarda necesaria: sin tamano
// no hay escala a la que reescalar las coordenadas). Con el panel repartido
// en secciones, la del mapa esta oculta casi siempre -> el lienzo se quedaba
// VACIO, y por eso el mapa no salia en el PDF.
//
// Aqui se le devuelve el tamano el instante justo: se descubre la seccion,
// se pinta y se vuelve a ocultar, todo seguido dentro del mismo cuadro de
// animacion. El navegador no llega a pintar el estado intermedio, asi que
// no hay parpadeo, y el lienzo queda listo para cuando alguien imprima.
//
// No se usa el evento 'beforeprint' -que seria lo natural- porque no todos
// los caminos de impresion lo disparan (Chrome en modo headless con
// --print-to-pdf no lo hace), y el reporte tiene que salir completo siempre.
// Exportar el reporte a PDF.
//
// No basta con `window.print()`. El panel esta repartido en secciones y las
// inactivas van con `display:none`; el mapa de calor, que es un <canvas>
// pintado por heatmap.js, no llegaba al PDF -comprobado: con la seccion del
// mapa activa el PDF trae el lienzo, y con otra activa no-. Confiar en que
// una regla @media print lo destape no alcanza: en la impresion la seccion
// aparece, pero el lienzo no viaja con ella.
//
// Aqui se destapan TODAS las secciones de verdad, en pantalla, se repinta
// cada mapa ya con su tamano real, y recien entonces se imprime.
// `window.print()` bloquea hasta que se cierra el dialogo, asi que al
// volver se deshace el destape y se vuelve a pintar como estaba.
function exportarReportePDF() {
  document.body.classList.add('destapar-secciones');
  void document.body.offsetHeight;   // fuerza el recalculo antes de medir
  if (state.mostrandoComparacion) {
    pintarHeatmap('positions-heatmap-canvas-a', state.compareAPositions);
    pintarHeatmap('positions-heatmap-canvas-b', state.compareBPositions);
  } else {
    pintarHeatmap('positions-heatmap-canvas', state.positions);
  }
  try {
    window.print();
  } finally {
    document.body.classList.remove('destapar-secciones');
    render();
  }
}

function pintarMapaAunqueOculto(containerId, positions) {
  const cont = document.getElementById(containerId);
  if (!cont) return;
  const seccion = cont.closest('.panel-seccion');
  const oculta = seccion && !seccion.classList.contains('activa');
  if (oculta) seccion.style.display = 'block';
  pintarHeatmap(containerId, positions);
  if (oculta) seccion.style.display = '';
}

function fillCountUps() {
  const isNewVideo = state.videoDetail && state.videoDetail.video_id !== lastCountedVideoId;
  document.querySelectorAll('[data-count-target]').forEach((el) => {
    const target = Number(el.dataset.countTarget);
    if (isNewVideo) animateCount(el, target, 650);
    else el.textContent = formatNumber(target);
  });
  if (state.videoDetail) lastCountedVideoId = state.videoDetail.video_id;
}

function animateCount(el, to, duration) {
  const start = performance.now();
  function tick(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = t <= 0 ? 0 : 1 - Math.pow(2, -10 * t);
    el.textContent = formatNumber(Math.round(to * eased));
    if (t < 1) requestAnimationFrame(tick);
    else el.textContent = formatNumber(to);
  }
  requestAnimationFrame(tick);
}

document.addEventListener('click', async (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.dataset.action;

  if (action === 'entrar-panel') irA('panel');
  else if (action === 'volver-inicio') irA('inicio');
  else if (action === 'exportar-pdf') exportarReportePDF();
  else if (action === 'exportar-csv') exportarCSV();
  else if (action === 'open-settings') setState({ isConfigModalOpen: true, configTest: null, configUrlDraft: null });
  else if (action === 'toggle-dark-mode') {
    const nuevo = !state.darkMode;
    localStorage.setItem('gondola_dark_mode', String(nuevo));
    setState({ darkMode: nuevo });
  }
  else if (action === 'close-settings') setState({ isConfigModalOpen: false, configTest: null, configUrlDraft: null });
  else if (action === 'mostrar-info') setState({ infoAbierto: { titulo: el.dataset.infoTitulo, texto: el.dataset.infoTexto } });
  else if (action === 'cerrar-info') setState({ infoAbierto: null });
  else if (action === 'refresh-videos') loadVideos();
  else if (action === 'eliminar-video') {
    const actual = state.videos.find((v) => v.video_id === state.selectedVideoId);
    const nombre = actual ? (actual.source_name || actual.video_id) : state.selectedVideoId;
    // confirm() nativo, no un modal propio: es una unica pregunta de
    // si/no antes de una accion que NO se puede deshacer (borra archivos
    // del servidor, no solo la fila de la lista) -no hace falta mas
    // ceremonia que esa para algo tan puntual.
    if (window.confirm(`¿Eliminar "${nombre}"?\n\nEsto borra el video de la base de datos y TODOS sus archivos en el servidor (video, render, calibración). No se puede deshacer.`)) {
      eliminarVideoActual();
    }
  }
  else if (action === 'retry-detail') loadVideoDetail(state.selectedVideoId);
  else if (action === 'retry-health') verifyHealth();
  else if (action === 'enable-mock') toggleMockMode(true);
  else if (action === 'toggle-mock-in-modal') toggleMockMode(!state.useMockMode);
  else if (action === 'ir-seccion') {
    const seccion = el.dataset.seccion;
    // Se recuerda por navegador: quien vive en el mapa de calor lo vuelve a
    // encontrar abierto la proxima vez, sin pasar por el resumen.
    localStorage.setItem('gondola_panel_seccion', seccion);
    setState({ panelSeccion: seccion });
  }
  else if (action === 'zones-view-table') setState({ zonesViewMode: 'table' });
  else if (action === 'zones-view-cards') setState({ zonesViewMode: 'cards' });
  else if (action === 'abrir-comparacion') {
    // #/comparar es su PROPIA ruta en el hash (distinta de #/panel, ver el
    // comentario de mostrandoComparacion en estado.js) -asi ATRAS desde
    // comparar vuelve al video unico, no salta directo a la portada.
    irA('comparar');
    if (!state.compareA && state.selectedVideoId) loadCompareData('A', state.selectedVideoId);
  }
  else if (action === 'cerrar-comparacion') irA('panel');
  else if (action === 'abrir-subida') abrirSubida();
  else if (action === 'subida-cerrar') cerrarSubida();
  else if (action === 'subida-reiniciar') abrirSubida();
  else if (action === 'subida-enviar') subirVideo();
  else if (action === 'subida-zonas') enviarZonas();
  else if (action === 'borrar-rect') {
    const i = Number(el.dataset.indice);
    actualizarSubida({ rects: state.subida.rects.filter((_, n) => n !== i) });
  }
  else if (action === 'subida-ver') {
    const id = state.subida.job && state.subida.job.video_id;
    cerrarSubida();
    if (id) { setState({ selectedVideoId: id }); selectVideo(id); }
  }
  else if (action === 'reset-default-url') { setState({ configUrlDraft: DEFAULT_API_BASE_URL }); }
  else if (action === 'test-connection') {
    const url = document.getElementById('api-base-url-input').value;
    setState({ configTesting: true, configTest: null, configUrlDraft: url });
    try {
      const res = await checkBackendHealth(url);
      setState({ configTesting: false, configTest: { success: true, message: `Conexión exitosa: GET /health respondió status "${res.status}"` } });
    } catch (err) {
      setState({ configTesting: false, configTest: { success: false, message: `No se pudo conectar: ${err.message}. Asegúrate de que el backend FastAPI esté corriendo en ${url}.` } });
    }
  }
  else if (action === 'save-settings') {
    const url = document.getElementById('api-base-url-input').value.trim();
    localStorage.setItem('gondola_api_base_url', url);
    state.apiBaseUrl = url;
    state.isConfigModalOpen = false;
    state.configTest = null;
    state.configUrlDraft = null;
    render();
    verifyHealth();
    loadVideos();
  }
});

document.addEventListener('input', (e) => {
  // Sin render() aqui a proposito: solo guarda lo que la persona ya ve
  // escrito, para que un setState() disparado por otra cosa (el fetch de
  // "Probar", por ejemplo) no lo borre. Ver el docstring de configUrlDraft.
  if (e.target.id === 'api-base-url-input') state.configUrlDraft = e.target.value;
  // Los nombres de los estantes y de la gondola se guardan SIN render(),
  // por el mismo motivo que la URL de arriba: repintar en cada tecla
  // reconstruiria el input y se perderia el cursor a media palabra.
  else if (e.target.id === 'nombre-gondola') state.subida.nombreGondola = e.target.value;
  else if (e.target.dataset.rectNombre !== undefined) {
    const r = state.subida.rects[Number(e.target.dataset.rectNombre)];
    if (r) { r.name = e.target.value; pintarLienzo(); }
  }
  else if (e.target.dataset.rectCategoria !== undefined) {
    const r = state.subida.rects[Number(e.target.dataset.rectCategoria)];
    if (r) r.categoria = e.target.value;
  }
});

document.addEventListener('change', (e) => {
  if (e.target.id === 'video-select') selectVideo(e.target.value);
  else if (e.target.id === 'archivo-subida') actualizarSubida({ archivo: e.target.files[0] || null, error: null });
  else if (e.target.dataset.termino) {
    actualizarSubida({ terminos: { ...state.subida.terminos, [e.target.dataset.termino]: e.target.checked } });
  }
  else if (e.target.dataset.compareSlot) loadCompareData(e.target.dataset.compareSlot, e.target.value);
  else if (e.target.id === 'heatmap-style-select') {
    localStorage.setItem('gondola_heatmap_style', e.target.value);
    setState({ heatmapStyle: e.target.value });
  }
});

render();
arrancar();
