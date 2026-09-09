// El portal del video anonimizado
// Parte del dashboard de Gondola Inteligente. Se carga desde index.html
// como <script> clasico (no modulo ES): ver el comentario de index.html.

// Crea un <video> que vive en un portal FUERA de #root y nunca se destruye.
// render() reemplaza #root entero varias veces mientras el video descarga
// (zonas, posiciones y metricas llegan por separado), y un <video> a medio
// descargar no sobrevive a eso: el navegador lo reporta como error de
// reproduccion aunque el servidor haya respondido bien. El portal solo se
// reposiciona con CSS encima del hueco que deja el placeholder.
//
// Hacen falta dos: uno para el panel y el "Video A" de la comparacion, y
// otro para el "Video B".
function crearReproductorPersistente(portalId) {
  const portal = document.getElementById(portalId);
  const video = document.createElement('video');
  video.controls = true;
  video.preload = 'metadata';
  video.style.width = '100%';
  video.style.height = '100%';
  video.style.borderRadius = '0.5rem';
  video.style.display = 'block';

  const errorBox = document.createElement('p');
  errorBox.hidden = true;
  errorBox.className = 'text-xs text-[#956400] bg-[#FBF3DB] rounded-lg px-3 py-2.5 mt-2';
  errorBox.textContent = 'Este video todavía no tiene un render "privacy" generado en el servidor (o la API no responde).';

  portal.appendChild(video);
  portal.appendChild(errorBox);
  video.addEventListener('error', () => {
    video.style.display = 'none';
    errorBox.hidden = false;
  });

  let ultimoSrc = null;

  function posicionar(placeholderId) {
    const placeholder = document.getElementById(placeholderId);
    // Sin hueco donde encajar, el portal se esconde Y se pausa: si solo se
    // escondiera, el video seguiria corriendo (y sonando) invisible.
    if (!placeholder) { portal.hidden = true; video.pause(); return null; }
    const rect = placeholder.getBoundingClientRect();
    // El hueco puede EXISTIR y aun asi no verse: desde que el panel se
    // divide en secciones, las que no estan activas se ocultan con
    // `display:none` y su rectangulo mide 0x0. Sin esto el portal se
    // colocaba en la esquina superior izquierda con tamano cero -invisible,
    // pero con el video descargando y sonando.
    if (!rect.width || !rect.height) { portal.hidden = true; video.pause(); return null; }
    portal.style.top = `${window.scrollY + rect.top}px`;
    portal.style.left = `${window.scrollX + rect.left}px`;
    portal.style.width = `${rect.width}px`;
    portal.style.height = `${rect.height}px`;
    portal.hidden = false;
    return placeholder;
  }

  return {
    init(placeholderId, src) {
      const placeholder = posicionar(placeholderId);
      if (!placeholder) return;
      if (src === ultimoSrc) return; // mismo video: no tocar .src o se reinicia la carga sin necesidad
      ultimoSrc = src;
      video.style.display = 'block';
      errorBox.hidden = true;
      video.src = src;
    },
    // Ocultar SIEMPRE pausa. Un <video> escondido que sigue corriendo gasta
    // CPU, sigue descargando y -lo peor- se sigue oyendo.
    ocultar() { portal.hidden = true; video.pause(); },
    reposicionar(placeholderId) { if (!portal.hidden) posicionar(placeholderId); },
  };
}

const reproductorA = crearReproductorPersistente('video-player-portal');
const reproductorB = crearReproductorPersistente('video-compare-b-portal');

/** Esconde los dos reproductores. Hace falta en cada pantalla que NO tenga
 *  hueco para ellos: como los portales viven FUERA de #root, reemplazar
 *  #root no se los lleva por delante -se quedaban flotando encima de la
 *  portada, con el video sonando (bug real, visto en pantalla)-. */
function ocultarReproductores() {
  reproductorA.ocultar();
  reproductorB.ocultar();
}

window.addEventListener('resize', () => {
  if (state.mostrandoComparacion) {
    reproductorA.reposicionar('video-compare-a-placeholder');
    reproductorB.reposicionar('video-compare-b-placeholder');
  } else {
    reproductorA.reposicionar('video-player-placeholder');
  }
});

function _urlDeRender(videoId) {
  // El navegador puede haber cacheado una copia del video de ANTES de que
  // se reprocesara (ej. un contador nuevo en la cabecera): Ctrl+Shift+R no
  // lo evita, porque este <video> se carga por JavaScript, no como parte
  // de la navegacion inicial de la pagina (ver crearReproductorPersistente,
  // el patron "portal"). `processed_at` cambia cada vez que el video se
  // reprocesa, asi que agregarlo como query string vuelve la URL distinta
  // y fuerza una descarga nueva -sin esto, Cache-Control: no-cache en
  // backend/api.py no sirve de nada si el navegador nunca vuelve a
  // preguntarle al servidor-.
  const video = state.videos.find((v) => v.video_id === videoId);
  const base = `${cleanBaseUrl(state.apiBaseUrl)}/videos/${encodeURIComponent(videoId)}/render`;
  return video?.processed_at ? `${base}?processed_at=${encodeURIComponent(video.processed_at)}` : base;
}

function _initSlot(reproductor, placeholderId, videoId) {
  if (!videoId || isDemoVideo(videoId)) { reproductor.ocultar(); return; }
  reproductor.init(placeholderId, _urlDeRender(videoId));
}

function initVideoPlayer() {
  // Con un modal abierto, los reproductores se esconden. No es una mania:
  // #root lleva `position:relative; z-index:1`, y eso CREA UN CONTEXTO DE
  // APILAMIENTO -todo lo que vive dentro, incluido un modal `z-50`, queda
  // encerrado en el nivel 1-. Los portales son hermanos de #root con
  // z-index:5, asi que pintan por encima del modal entero (bug real: el
  // video se veia atravesando la ventana de "Subir un video").
  //
  // Subir el z-index del modal no arregla nada (esta dentro de #root), y
  // bajar el del portal lo esconderia detras de la tarjeta. Esconderlo
  // mientras hay modal es lo correcto: detras de un modal no se ve igual.
  //
  // infoAbierto (el modal de "de donde sale este dato", ver
  // vista-modales.js/renderInfoModal) es el mismo caso: sin esto el video
  // pintaba encima del modal y su boton de cerrar quedaba inalcanzable
  // -bug real, visto en pantalla, solo se salia con F5-.
  if (state.isConfigModalOpen || state.subida.abierto || state.infoAbierto) {
    ocultarReproductores();
    return;
  }
  if (state.mostrandoComparacion) {
    _initSlot(reproductorA, 'video-compare-a-placeholder', state.compareA);
    _initSlot(reproductorB, 'video-compare-b-placeholder', state.compareB);
  } else {
    _initSlot(reproductorA, 'video-player-placeholder', state.selectedVideoId);
    reproductorB.ocultar();
  }
}
