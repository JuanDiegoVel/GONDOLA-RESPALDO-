// El estado y su carga desde la API
// Parte del dashboard de Gondola Inteligente. Se carga desde index.html
// como <script> clasico (no modulo ES): ver el comentario de index.html.

// Cada carga de pagina (recargar, reabrir la pestaña, escanear el QR otra
// vez) arranca SIEMPRE en la portada -aunque el navegador recuerde
// #/panel o #/comparar de una visita anterior-, para que nadie se salte
// la explicacion inicial solo porque ya habia entrado antes. Corre ANTES
// de construir `state` (justo abajo, mostrandoInicio lee rutaActual())
// para que ni el primer render() vea el hash viejo: si esto viviera
// dentro de arrancar() (que es async y corre despues del primer render(),
// ver el final de app.js), se alcanzaria a pintar el panel un instante
// antes de saltar a la portada.
if (location.hash !== '#/inicio') {
  history.replaceState(null, '', `${location.pathname}${location.search}#/inicio`);
}

// Todo el estado de la pantalla vive aqui, en un solo objeto plano.
const state = {
  // Pantalla de bienvenida: lo primero que se ve al abrir el archivo,
  // antes de tocar la API o el modo demo. Se apaga con el boton "Entrar
  // al panel" (ver renderPantallaInicio), y con #/inicio, #/panel y
  // #/comparar en la URL (ver rutaActual()/sincronizarConRuta(), en
  // utils.js, y el listener de 'hashchange' en arrancar(), mas abajo) el
  // boton ATRAS del navegador navega entre esas tres pantallas en vez de
  // sacar de la pagina -bug real, reportado por un companero de equipo-.
  // Pero SIEMPRE arranca en la portada (ver el bloque justo arriba): un
  // #/panel guardado de una visita anterior ya no la salta.
  mostrandoInicio: rutaActual() === 'inicio',
  // Modo oscuro: se recuerda por navegador (localStorage). Si nunca se ha
  // tocado el interruptor, arranca OSCURO -no siguiendo al sistema, como
  // antes-. El oscuro es el tema para el que se diseno la interfaz, y la
  // escena de uso manda: esto se presenta proyectado en un salon y se
  // consulta en la trastienda de una tienda, no en una oficina soleada.
  // El interruptor sigue ahi y su eleccion sigue mandando sobre esto.
  darkMode: localStorage.getItem('gondola_dark_mode') !== null
    ? localStorage.getItem('gondola_dark_mode') === 'true'
    : true,
  // Seccion activa del panel. El panel dejo de ser un unico scroll larguisimo
  // y se reparte en secciones que se eligen en la barra lateral. Vive en el
  // estado (y se recuerda por navegador), NO en el hash de la URL: el hash
  // ya lo usan inicio/panel/comparar, con un arreglo de un companero que
  // fuerza #/inicio en cada carga -meter subrutas ahi era arriesgar ese
  // comportamiento a cambio de nada.
  panelSeccion: localStorage.getItem('gondola_panel_seccion') || 'resumen',
  // Estilo del mapa de calor real (ver HEATMAP_ESTILOS): un solo estilo
  // para toda la pantalla (principal y comparacion), no uno por video.
  heatmapStyle: localStorage.getItem('gondola_heatmap_style') || 'contraste',
  apiBaseUrl: localStorage.getItem('gondola_api_base_url') || DEFAULT_API_BASE_URL,
  useMockMode: localStorage.getItem('gondola_use_mock_mode') !== null
    ? localStorage.getItem('gondola_use_mock_mode') === 'true'
    : true,
  isBackendHealthy: null,
  isCheckingHealth: false,
  videos: [],
  selectedVideoId: '',
  videoDetail: null,
  zoneMetrics: [],                 // filas de GET /videos/{id}/metrics (una por zona)
  zoneHierarchy: [],               // filas de GET /videos/{id}/zones (gondola/estante + parent_zone_id)
  isLoadingHierarchy: false,
  positions: [],                   // filas de GET /videos/{id}/positions ({x,y} en pixeles del frame)
  isLoadingPositions: false,
  // Comparacion: apartado APARTE del panel principal (ver
  // renderComparisonView, en vista-comparar.js), no una tarjeta mas de la
  // pantalla de un solo video. Mezclar los dos causaba un bug real de
  // reproductor de video que a veces se quedaba en blanco al volver de
  // comparar a ver un solo video -el mismo <video> vivo se ocultaba y
  // mostraba sin avisarle al navegador, y a veces la carga en curso se
  // perdia-. Con vistas separadas cada una tiene su propio hueco para el
  // video, sin pisarse. #/comparar tiene su PROPIA ruta en el hash
  // (distinta de #/panel): antes las dos compartian #/panel, y el boton
  // ATRAS desde comparar saltaba directo a la portada sin pasar por el
  // video unico -pedido explicito, para que el historial del navegador
  // distinga las tres pantallas de verdad-.
  mostrandoComparacion: rutaActual() === 'comparar',
  // Cada slot (A/B) trae el mismo paquete completo de datos que trae el
  // video principal (loadVideoDetail/loadVideoMetrics/loadZoneHierarchy/
  // loadPositions), para poder mostrar TODO -resumen, zonas, mapa de
  // calor, retroalimentacion- de los dos videos a la vez, no solo 4
  // numeros sueltos.
  compareA: '', compareADetail: null, isLoadingCompareA: false,
  compareAMetrics: [], isLoadingCompareAMetrics: false,
  compareAHierarchy: [], isLoadingCompareAHierarchy: false,
  compareAPositions: [], isLoadingCompareAPositions: false,
  compareB: '', compareBDetail: null, isLoadingCompareB: false,
  compareBMetrics: [], isLoadingCompareBMetrics: false,
  compareBHierarchy: [], isLoadingCompareBHierarchy: false,
  compareBPositions: [], isLoadingCompareBPositions: false,
  subida: SUBIDA_VACIA(),
  isLoadingVideos: false,
  isLoadingDetail: false,
  isLoadingMetrics: false,
  isDeletingVideo: false,
  errorVideos: null,
  errorDetail: null,
  errorMetrics: null,
  isConfigModalOpen: false,
  // {titulo, texto} de la tarjeta cuyo infoButton() se toco, o null si el
  // modal de "de donde sale este dato" (renderInfoModal(), vista-modales.js)
  // esta cerrado.
  infoAbierto: null,
  // Borrador del campo de URL en el modal de configuracion: separado de
  // apiBaseUrl (la URL ya aplicada) para que escribir una URL nueva y
  // pulsar "Probar" no la borre. "Probar" dispara un fetch async que
  // termina en setState() -> render(), y render() reconstruye el <input>
  // entero desde state; si el value="" leyera apiBaseUrl directamente, el
  // re-render posterior a la prueba pisaba lo que la persona acababa de
  // escribir con el valor viejo ya guardado (bug real, visto probando el
  // dashboard: la prueba de conexion evaluaba la URL escrita, pero el
  // campo volvia a mostrar la URL anterior apenas llegaba la respuesta).
  configUrlDraft: null,
  zonesViewMode: 'table',
  configTest: null,
  configTesting: false,
};

function setState(patch) { Object.assign(state, patch); render(); }

async function verifyHealth() {
  setState({ isCheckingHealth: true });
  try {
    const res = await checkBackendHealth(state.apiBaseUrl);
    setState({ isBackendHealthy: res.status === 'ok', isCheckingHealth: false });
  } catch {
    setState({ isBackendHealthy: false, isCheckingHealth: false });
  }
}

async function loadVideos() {
  setState({ isLoadingVideos: true, errorVideos: null });
  try {
    const data = await getVideos(state.apiBaseUrl, state.useMockMode);
    const exists = data.some((v) => v.video_id === state.selectedVideoId);
    // Sin auto-elegir el primero: si el video que ya estaba elegido sigue
    // existiendo, se queda; si no (o si nunca se habia elegido ninguno),
    // se deja vacio -la persona elige, el panel no le impone un video-.
    setState({
      videos: data,
      isLoadingVideos: false,
      selectedVideoId: exists ? state.selectedVideoId : '',
      videoDetail: exists ? state.videoDetail : null,
      zoneMetrics: exists ? state.zoneMetrics : [],
    });
    if (state.selectedVideoId) {
      loadVideoDetail(state.selectedVideoId);
      loadVideoMetrics(state.selectedVideoId);
      loadZoneHierarchy(state.selectedVideoId);
      loadPositions(state.selectedVideoId);
    }
  } catch (err) {
    setState({ errorVideos: err.message || 'Error de red al conectar con GET /videos', isLoadingVideos: false });
  }
}

async function loadVideoDetail(videoId) {
  if (!videoId) return;
  setState({ isLoadingDetail: true, errorDetail: null });
  try {
    const detail = await getVideoDetail(state.apiBaseUrl, videoId, state.useMockMode);
    setState({ videoDetail: detail, isLoadingDetail: false });
  } catch (err) {
    setState({ errorDetail: err.message || `Error al consultar detalles de ${videoId}`, videoDetail: null, isLoadingDetail: false });
  }
}

async function loadVideoMetrics(videoId) {
  if (!videoId) return;
  setState({ isLoadingMetrics: true, errorMetrics: null });
  try {
    const metrics = await getVideoMetrics(state.apiBaseUrl, videoId, state.useMockMode);
    setState({ zoneMetrics: metrics, isLoadingMetrics: false });
  } catch (err) {
    setState({ errorMetrics: err.message || `Error al consultar metricas de zonas para ${videoId}`, zoneMetrics: [], isLoadingMetrics: false });
  }
}

// Trae la jerarquia de zonas (que estante pertenece a que gondola) para
// poder agrupar el mapa de calor. Es un pedido APARTE de loadVideoMetrics:
// metrics.js da los NUMEROS, este endpoint da la ESTRUCTURA (quien es hijo
// de quien). Se cruzan por zone_id al momento de dibujar.
async function loadZoneHierarchy(videoId) {
  if (!videoId) return;
  setState({ isLoadingHierarchy: true });
  try {
    const hierarchy = state.useMockMode
      ? MOCK_ZONE_HIERARCHY[videoId] || []
      : await fetchFromApi(`${cleanBaseUrl(state.apiBaseUrl)}/videos/${encodeURIComponent(videoId)}/zones`);
    setState({ zoneHierarchy: hierarchy, isLoadingHierarchy: false });
  } catch {
    setState({ zoneHierarchy: [], isLoadingHierarchy: false });
  }
}

// Punto de apoyo (los pies) de cada evento del video, en pixeles del frame
// original -la materia prima de un mapa de calor REAL (densidad espacial),
// no un agregado por zona. Puede ser una lista larga (miles de puntos):
// se pide una sola vez por video, no en cada render().
async function loadPositions(videoId) {
  if (!videoId) return;
  setState({ isLoadingPositions: true });
  try {
    const positions = state.useMockMode
      ? MOCK_POSITIONS[videoId] || []
      : await fetchFromApi(`${cleanBaseUrl(state.apiBaseUrl)}/videos/${encodeURIComponent(videoId)}/positions`);
    setState({ positions, isLoadingPositions: false });
  } catch {
    setState({ positions: [], isLoadingPositions: false });
  }
}

// Trae el PAQUETE COMPLETO (detalle + metricas + jerarquia de zonas +
// posiciones) de un video para la vista de comparacion (ver
// renderComparisonView, en vista-comparar.js) -el mismo paquete que trae
// selectVideo() para el video principal, para que la comparacion pueda
// mostrar TODO de cada lado, no solo 4 numeros sueltos-. `slot` es 'A' o
// 'B': cada lado se carga y guarda aparte, para poder cambiar uno sin
// perder el otro.
async function loadCompareData(slot, videoId) {
  const k = (sufijo) => `compare${slot}${sufijo}`;

  if (!videoId) {
    setState({
      [k('')]: '', [k('Detail')]: null,
      [k('Metrics')]: [], [k('Hierarchy')]: [], [k('Positions')]: [],
    });
    return;
  }
  setState({ [k('')]: videoId, [`isLoadingCompare${slot}`]: true });
  try {
    const detail = await getVideoDetail(state.apiBaseUrl, videoId, state.useMockMode);
    setState({ [k('Detail')]: detail, [`isLoadingCompare${slot}`]: false });
  } catch {
    setState({ [k('Detail')]: null, [`isLoadingCompare${slot}`]: false });
  }

  setState({ [`isLoadingCompare${slot}Metrics`]: true });
  try {
    const metrics = await getVideoMetrics(state.apiBaseUrl, videoId, state.useMockMode);
    setState({ [k('Metrics')]: metrics, [`isLoadingCompare${slot}Metrics`]: false });
  } catch {
    setState({ [k('Metrics')]: [], [`isLoadingCompare${slot}Metrics`]: false });
  }

  setState({ [`isLoadingCompare${slot}Hierarchy`]: true });
  try {
    const hierarchy = state.useMockMode
      ? MOCK_ZONE_HIERARCHY[videoId] || []
      : await fetchFromApi(`${cleanBaseUrl(state.apiBaseUrl)}/videos/${encodeURIComponent(videoId)}/zones`);
    setState({ [k('Hierarchy')]: hierarchy, [`isLoadingCompare${slot}Hierarchy`]: false });
  } catch {
    setState({ [k('Hierarchy')]: [], [`isLoadingCompare${slot}Hierarchy`]: false });
  }

  setState({ [`isLoadingCompare${slot}Positions`]: true });
  try {
    const positions = state.useMockMode
      ? MOCK_POSITIONS[videoId] || []
      : await fetchFromApi(`${cleanBaseUrl(state.apiBaseUrl)}/videos/${encodeURIComponent(videoId)}/positions`);
    setState({ [k('Positions')]: positions, [`isLoadingCompare${slot}Positions`]: false });
  } catch {
    setState({ [k('Positions')]: [], [`isLoadingCompare${slot}Positions`]: false });
  }
}

// Cuando se elige un video nuevo en el selector principal, se piden sus
// cuatro piezas de datos EN PARALELO (no una espera a la otra): el resumen,
// las metricas por zona, la jerarquia de zonas y las posiciones.
function selectVideo(videoId) {
  setState({ selectedVideoId: videoId });
  loadVideoDetail(videoId);
  loadVideoMetrics(videoId);
  loadZoneHierarchy(videoId);
  loadPositions(videoId);
}

function toggleMockMode(enabled) {
  localStorage.setItem('gondola_use_mock_mode', String(enabled));
  setState({ useMockMode: enabled });
  loadVideos();
}

// Borra el video elegido: su fila en PostgreSQL (con events/metrics en
// cascada) y todos sus archivos en el servidor (ver DELETE
// /videos/{video_id} en backend/api.py). No se puede deshacer -por eso
// quien llama a esto (el manejador de 'eliminar-video', en app.js) ya pidio
// confirmar antes-. No aplica en Modo Demostracion: los videos de ahi no
// son filas de verdad, no hay nada que borrar en la API.
async function eliminarVideoActual() {
  const videoId = state.selectedVideoId;
  if (!videoId || state.useMockMode) return;
  setState({ isDeletingVideo: true });
  try {
    await deleteVideo(state.apiBaseUrl, videoId);
    setState({
      isDeletingVideo: false,
      selectedVideoId: '', videoDetail: null,
      zoneMetrics: [], zoneHierarchy: [], positions: [],
    });
    loadVideos();
  } catch (err) {
    setState({ isDeletingVideo: false, errorVideos: `No se pudo borrar el video: ${err.message}` });
  }
}

// Arranque: pone el hash inicial si hace falta, engancha 'hashchange' (ver
// sincronizarConRuta(), en utils.js) para que el boton ATRAS del navegador
// funcione, y decide el modo demo si nadie lo ha elegido todavia (primera
// visita en este navegador) segun responda o no la API, en vez de imponerlo
// -con la API arriba se entra directo a los videos reales; sin ella se
// queda en demo, que es justo para lo que existe. Si la persona YA eligio
// con el interruptor de configuracion, esa decision manda y aqui no se
// toca nada.
async function arrancar() {
  // El hash ya quedo forzado a #/inicio (si hacia falta) ANTES de esto,
  // al construir `state` -ver el bloque al principio de este archivo-.
  // Aqui solo falta enganchar 'hashchange' para que la navegacion DENTRO
  // de esta visita (entrar al panel, comparar, el boton ATRAS) siga
  // funcionando con normalidad.
  window.addEventListener('hashchange', sincronizarConRuta);

  await verifyHealth();
  if (localStorage.getItem('gondola_use_mock_mode') === null && state.isBackendHealthy) {
    setState({ useMockMode: false });
  }
  loadVideos();
}
