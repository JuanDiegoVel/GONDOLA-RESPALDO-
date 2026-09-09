// Modal de configuracion y portada de bienvenida
// Parte del dashboard de Gondola Inteligente. Se carga desde index.html
// como <script> clasico (no modulo ES): ver el comentario de index.html.

function renderConfigModal() {
  if (!state.isConfigModalOpen) return '';
  const testResultHtml = !state.configTest ? '' : `
    <div class="p-3 rounded-lg border text-xs flex items-start gap-2 ${state.configTest.success ? 'bg-emerald-50 border-emerald-200 text-emerald-900' : 'bg-amber-50 border-amber-200 text-amber-900'}">
      ${state.configTest.success ? icon('check-circle-2', 'w-4 h-4 text-emerald-600 shrink-0 mt-0.5') : icon('alert-triangle', 'w-4 h-4 text-amber-600 shrink-0 mt-0.5')}
      <div class="leading-relaxed">${esc(state.configTest.message)}</div>
    </div>`;

  return `
  <div role="dialog" aria-modal="true" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs modal-backdrop">
    <div class="bg-white rounded-2xl max-w-lg w-full border border-slate-200 shadow-xl overflow-hidden modal-anim">
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
        <div class="flex items-center gap-2.5">
          <div class="p-2 rounded-lg bg-slate-900 text-white">${icon('server', 'w-4 h-4')}</div>
          <div>
            <h2 class="text-sm font-bold text-slate-900">Configuración de la API REST (FastAPI)</h2>
            <p class="text-xs text-slate-500">Conexión exclusiva con el backend de Góndola Inteligente</p>
          </div>
        </div>
        <button type="button" data-action="close-settings" class="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition-colors" aria-label="Cerrar ventana">${icon('x', 'w-4 h-4')}</button>
      </div>
      <div class="p-6 space-y-5">
        <div class="p-3.5 rounded-xl border border-slate-200 bg-slate-50 flex items-start justify-between gap-3">
          <div class="space-y-0.5">
            <div class="flex items-center gap-2">${icon('database', 'w-4 h-4 text-indigo-600')}<span class="text-xs font-bold text-slate-900">Modo Datos de Demostración (Contrato Oficial)</span></div>
            <p class="text-xs text-slate-500 leading-relaxed">Útil para explorar la interfaz sin requerir el backend FastAPI corriendo localmente. Replica con precisión los endpoints y esquemas requeridos.</p>
          </div>
          <button type="button" data-action="toggle-mock-in-modal" class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${state.useMockMode ? 'bg-indigo-600' : 'bg-slate-300'}">
            <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${state.useMockMode ? 'translate-x-5' : 'translate-x-0'}"></span>
          </button>
        </div>
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <label for="api-base-url-input" class="text-xs font-semibold text-slate-700">Base URL de la API (Python FastAPI):</label>
            <button type="button" data-action="reset-default-url" class="text-[11px] text-indigo-600 hover:underline">Restablecer (127.0.0.1:8000)</button>
          </div>
          <div class="flex gap-2">
            <input id="api-base-url-input" type="text" value="${esc(state.configUrlDraft ?? state.apiBaseUrl)}" placeholder="http://127.0.0.1:8000"
                   class="flex-1 px-3 py-2 text-sm font-mono bg-white border border-slate-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500" />
            <button type="button" data-action="test-connection" ${state.configTesting ? 'disabled' : ''} class="px-3 py-2 text-xs font-semibold rounded-lg border border-slate-300 bg-slate-50 hover:bg-slate-100 text-slate-700 transition-colors inline-flex items-center gap-1.5 disabled:opacity-50">
              ${state.configTesting ? icon('refresh-cw', 'w-3.5 h-3.5 animate-spin text-slate-500') : icon('server', 'w-3.5 h-3.5 text-slate-500')} Probar
            </button>
          </div>
          <p class="text-[11px] text-slate-500">Valor por defecto: <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700">http://127.0.0.1:8000</code>. Se consulta el endpoint <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700">GET /health</code>.</p>
        </div>
        ${testResultHtml}
        <div class="pt-2 border-t border-slate-100">
          <h4 class="text-xs font-semibold text-slate-700 mb-1.5 flex items-center gap-1">${icon('help-circle', 'w-3.5 h-3.5 text-slate-400')} Endpoints de solo lectura consumidos:</h4>
          <div class="text-[11px] font-mono text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-200 space-y-1">
            <div>GET /health</div><div>GET /videos</div><div>GET /videos/{video_id}</div><div>GET /videos/{video_id}/metrics</div><div>GET /videos/{video_id}/zones</div>
          </div>
        </div>
      </div>
      <div class="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2">
        <button type="button" data-action="close-settings" class="px-3.5 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-200/70 transition-colors">Cancelar</button>
        <button type="button" data-action="save-settings" class="px-4 py-2 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 rounded-lg shadow-xs transition-colors">Guardar y Aplicar</button>
      </div>
    </div>
  </div>`;
}

// Modal generico que abre cualquier infoButton() (ver vista-panel.js): un
// solo modal reutilizado por TODAS las tarjetas del dashboard, en vez de
// uno por tarjeta -el texto que muestra viene del propio boton que lo
// abrio (state.infoAbierto = {titulo, texto}, puesto en app.js), no de una
// lista aparte que alguien pueda olvidar mantener sincronizada.
function renderInfoModal() {
  const info = state.infoAbierto;
  if (!info) return '';
  return `
  <div role="dialog" aria-modal="true" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs modal-backdrop">
    <div class="bg-white rounded-2xl max-w-md w-full border border-slate-200 shadow-xl overflow-hidden modal-anim">
      <div class="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
        <div class="flex items-center gap-2.5">
          <div class="p-2 rounded-lg bg-[#1F6C9F] text-white">${icon('help-circle', 'w-4 h-4')}</div>
          <h2 class="text-sm font-bold text-slate-900">${esc(info.titulo)}</h2>
        </div>
        <button type="button" data-action="cerrar-info" class="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition-colors" aria-label="Cerrar ventana">${icon('x', 'w-4 h-4')}</button>
      </div>
      <div class="p-5">
        <p class="text-sm text-slate-600 leading-relaxed">${esc(info.texto)}</p>
      </div>
    </div>
  </div>`;
}

// Portada de bienvenida: que se ve esta pagina, que puede hacer, con que
// esta hecha -"muy por encimita", nada tecnico a fondo- y el logo en el
// centro. Vive fuera del <main> normal a proposito: es su propia pantalla
// completa, sin la barra de navegacion ni el resto del dashboard detras.
// Portada. Es el unico momento "de convencer" de todo el producto -lo
// primero que ve un jurado-, asi que no sigue las reglas del panel: aqui
// la composicion manda sobre la densidad.
//
// Antes era una pila vertical de tarjetas del mismo tamano (ilustracion,
// lista, nota) sobre fondo. Ahora es una sola composicion a dos columnas
// en escritorio: el argumento y la accion a la izquierda, el diagrama -que
// ES la idea del producto: nunca un rostro, solo un punto en el piso- con
// el peso visual que merece a la derecha. En movil vuelve a una columna.
// Portada. Es el unico momento "de convencer" de todo el producto -lo
// primero que ve un jurado-, asi que no sigue las reglas del panel: aqui
// manda la composicion sobre la densidad, y va SIEMPRE oscura, sin seguir
// el interruptor de tema (ver la seccion 7 de css/estilos.css).
//
// La fotografia (assets/hero-gondola.jpg) es un recorte del mockup del
// equipo: solo la escena, sin el texto que traia quemado encima. Todo lo
// que se lee aqui es HTML de verdad -nitido a cualquier zoom,
// seleccionable, traducible y accesible-, no pixeles de una imagen.
function renderPantallaInicio() {
  // Las cuatro capacidades REALES del sistema. El mockup mostraba seis
  // tarjetas, pero dos repetian el texto de otras dos (un defecto de la
  // imagen generada): inventar dos capacidades para rellenar la rejilla
  // seria afirmar algo que el sistema no hace.
  const capacidades = [
    ['trend-up',    'Contar tráfico y medir cuánto tiempo se detiene la gente frente a un estante.'],
    ['sparkle',     'Detectar cuándo alguien toma o devuelve un producto, y calcular la tasa de rechazo.'],
    ['map',         'Un mapa de calor real, por coordenadas, de dónde circula la gente.'],
    ['layout-grid', 'Comparar dos videos lado a lado con su análisis completo.'],
  ];

  return `
  <div class="portada">
    <div class="portada-foto" aria-hidden="true">
      <img src="assets/hero-gondola.jpg" alt="" />
    </div>

    <!-- Angulos del marco: decorativos, por eso no los anuncia el lector
         de pantalla. -->
    <div class="portada-marco" aria-hidden="true">
      <span class="es-si"></span><span class="es-sd"></span>
      <span class="es-ii"></span><span class="es-id"></span>
    </div>

    <div class="portada-contenido min-h-screen flex flex-col justify-between px-6 sm:px-10 lg:px-16 py-10 lg:py-14">
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-8 items-center content-start lg:content-center flex-1">

        <div class="lg:col-span-6 xl:col-span-5">
          <h1 class="portada-titulo portada-entra font-bold text-[clamp(2.75rem,7.5vw,5.25rem)]">
            Góndola<br />Inteligente
          </h1>

          <div class="portada-entra-2 mt-7 flex items-start gap-3 max-w-[46ch]">
            <span class="shrink-0 mt-1 w-8 h-8 rounded-lg grid place-items-center"
                  style="border:1px solid rgb(255 255 255 / .16); color:#67E8F9" aria-hidden="true">
              ${icon('video-camera', 'w-4 h-4')}
            </span>
            <p class="text-[15px] sm:text-base leading-relaxed" style="color:#C6C2D6; text-wrap:pretty">
              Analiza video de cámaras de tienda para entender cómo se mueven los clientes
              frente a una góndola: cuántos pasan, dónde se detienen y qué productos tocan,
              <strong class="font-semibold" style="color:#F3F1FA">sin identificar a ninguna persona</strong>.
            </p>
          </div>

          <div class="portada-entra-3 mt-9 flex flex-wrap items-center gap-3">
            <button type="button" data-action="entrar-panel"
                    class="portada-cta inline-flex items-center justify-center gap-2 h-12 px-7 rounded-full text-sm font-bold">
              Entrar al panel ${icon('arrow-right', 'w-4 h-4')}
            </button>
            <span class="portada-pill inline-flex items-center gap-2 h-12 px-5 rounded-full text-sm font-semibold"
                  title="El sistema no realiza reconocimiento facial ni almacena datos personales.">
              ${icon('shield-check', 'w-4 h-4')} 100% anónimo
            </span>
          </div>
        </div>

        <div class="lg:col-span-6 xl:col-span-7 lg:pl-6 lg:self-end">
          <ul class="portada-entra-3 grid grid-cols-1 sm:grid-cols-2 gap-3 list-none p-0 m-0">
            ${capacidades.map(([ico, texto]) => `
            <li class="portada-tarjeta flex items-start gap-3 p-4">
              <span class="shrink-0 mt-0.5" style="color:#67E8F9" aria-hidden="true">${icon(ico, 'w-4 h-4')}</span>
              <span class="text-[13px] leading-snug" style="color:#D8D5E6">${texto}</span>
            </li>`).join('')}
          </ul>
        </div>

      </div>

      <div class="portada-entra-3 pt-8 flex items-center gap-3 flex-wrap"
           style="border-top:1px solid rgb(255 255 255 / .08)">
        <span class="portada-firma text-[13px]">CodeBolts</span>
        <span class="text-[11px]" style="color:#7E7996">HackTech 5.0 · 2026</span>
      </div>
    </div>
  </div>`;
}
