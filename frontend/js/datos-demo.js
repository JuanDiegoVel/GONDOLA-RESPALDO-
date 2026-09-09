// Datos ficticios del "Modo Datos de Demostracion"
// Parte del dashboard de Gondola Inteligente. Se carga desde index.html
// como <script> clasico (no modulo ES): ver el comentario de index.html.

const MOCK_VIDEOS = [
  { video_id: 'video_001', source_name: 'video_001.mp4', fps: 30.0, width: 920, height: 680, frame_count: 6080, duration_s: 202.633, contract_version: '1.0.0', processed_at: '2026-09-04T07:13:02.652179+00:00' },
  { video_id: 'video_demo_pasillo_01', source_name: 'camara_pasillo_norte.mp4', fps: 25.0, width: 1920, height: 1080, frame_count: 7500, duration_s: 300.0, contract_version: '1.0.0', processed_at: '2026-09-03T18:45:10.120000+00:00' },
  { video_id: 'video_demo_cabecera', source_name: 'cabecera_promocional_a.mp4', fps: 30.0, width: 1280, height: 720, frame_count: 4500, duration_s: 150.0, contract_version: '1.0.0', processed_at: '2026-09-02T11:20:00.000000+00:00' },
];
const MOCK_DETAILS = {
  video_001: { video_id: 'video_001', source_name: 'video_001.mp4', duration_s: 202.633, processed_at: '2026-09-04T07:13:02.652179+00:00', people_count: 16, interaction_count: 17, pick_up_count: 1, put_back_count: 0, average_dwell_time_s: 7.868949379 },
  video_demo_pasillo_01: { video_id: 'video_demo_pasillo_01', source_name: 'camara_pasillo_norte.mp4', duration_s: 300.0, processed_at: '2026-09-03T18:45:10.120000+00:00', people_count: 48, interaction_count: 35, pick_up_count: 12, put_back_count: 4, average_dwell_time_s: 14.35 },
  video_demo_cabecera: { video_id: 'video_demo_cabecera', source_name: 'cabecera_promocional_a.mp4', duration_s: 150.0, processed_at: '2026-09-02T11:20:00.000000+00:00', people_count: 9, interaction_count: 4, pick_up_count: 0, put_back_count: 0, average_dwell_time_s: 4.12 },
};

const MOCK_ZONE_HIERARCHY = {
  video_001: [
    { zone_id: 'gondola_A', name: 'Estantería única (cámara cenital)', level: 'gondola', product_category: null, parent_zone_id: null },
  ],
  video_demo_pasillo_01: [
    { zone_id: 'gondola_pasillo_norte', name: 'Góndola Pasillo Norte', level: 'gondola', product_category: null, parent_zone_id: null },
    { zone_id: 'estante_superior', name: 'Estante Superior (Nivel Ojos)', level: 'shelf', product_category: 'Snacks y Galletas Premium', parent_zone_id: 'gondola_pasillo_norte' },
    { zone_id: 'estante_inferior', name: 'Estante Inferior (Nivel Suelo)', level: 'shelf', product_category: 'Formatos Familiares Gran Volumen', parent_zone_id: 'gondola_pasillo_norte' },
  ],
  video_demo_cabecera: [
    { zone_id: 'cabecera_isla', name: 'Isla de Oferta Estacional', level: 'gondola', product_category: null, parent_zone_id: null },
  ],
};

// Puntos de apoyo (pies) sinteticos para el mapa de calor real en modo demo:
// mismo formato que devuelve GET /videos/{id}/positions ({x,y} en pixeles
// del frame), agrupados en "manchas" alrededor de puntos calientes
// inventados (frente a un estante, cerca de una cabecera) en vez de
// esparcidos uniformemente, para que la densidad se vea creible.
function _mancha(cx, cy, spreadX, spreadY, n, seed) {
  const puntos = [];
  let s = seed;
  const azar = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
  for (let i = 0; i < n; i++) {
    const u1 = azar() || 1e-6;
    const u2 = azar();
    const radio = Math.sqrt(-2 * Math.log(u1));
    const angulo = 2 * Math.PI * u2;
    puntos.push({
      x: Math.round(cx + radio * Math.cos(angulo) * spreadX),
      y: Math.round(cy + radio * Math.sin(angulo) * spreadY),
    });
  }
  return puntos;
}
const MOCK_POSITIONS = {
  video_001: [
    ..._mancha(300, 420, 70, 60, 60, 7),
    ..._mancha(620, 380, 90, 70, 50, 13),
    ..._mancha(180, 200, 50, 50, 25, 21),
  ],
  video_demo_pasillo_01: [
    ..._mancha(1350, 300, 140, 100, 90, 31),
    ..._mancha(1400, 700, 120, 90, 70, 47),
    ..._mancha(600, 500, 100, 150, 55, 59),
    ..._mancha(900, 900, 90, 80, 30, 71),
  ],
  video_demo_cabecera: [
    ..._mancha(640, 360, 160, 130, 70, 83),
    ..._mancha(300, 550, 80, 60, 20, 97),
  ],
};

// La calibracion de camara (floor_zone de cada estante) en modo demo:
// mismo formato que devuelve GET /videos/{id}/zones/geometry, con
// rectangulos elegidos para caer cerca de las manchas de MOCK_POSITIONS de
// arriba -asi la silueta de la gondola que dibuja _dibujarSiluetaGondola()
// (vista-zonas.js) queda donde de verdad hay densidad, no flotando suelta.
const MOCK_ZONES_GEOMETRY = {
  video_001: {
    frame_width: 920, frame_height: 680,
    shelves: [
      { zone_id: 'gondola_A:estante_1', gondola_zone_id: 'gondola_A', name: 'Estantería única', x: 100, y: 300, width: 700, height: 250 },
    ],
  },
  video_demo_pasillo_01: {
    frame_width: 1920, frame_height: 1080,
    shelves: [
      { zone_id: 'gondola_pasillo_norte:estante_superior', gondola_zone_id: 'gondola_pasillo_norte', name: 'Estante Superior (Nivel Ojos)', x: 1180, y: 180, width: 620, height: 320 },
      { zone_id: 'gondola_pasillo_norte:estante_inferior', gondola_zone_id: 'gondola_pasillo_norte', name: 'Estante Inferior (Nivel Suelo)', x: 480, y: 680, width: 620, height: 320 },
    ],
  },
  video_demo_cabecera: {
    frame_width: 1280, frame_height: 720,
    shelves: [
      { zone_id: 'cabecera_isla:estante_1', gondola_zone_id: 'cabecera_isla', name: 'Isla de Oferta Estacional', x: 150, y: 250, width: 900, height: 400 },
    ],
  },
};

const MOCK_METRICS = {
  video_001: [{ zone_id: 'gondola_A', name: 'Estanteria unica (camara cenital)', level: 'gondola', product_category: null, window_start_s: 0.0, window_end_s: 202.633, people_count: 16, interaction_count: 17, pick_up_count: 1, put_back_count: 0, average_dwell_time_s: 7.8689494, interaction_rate: 0.875, pick_up_rate: 0.0588235, conversion_rate: 0.0625 }],
  video_demo_pasillo_01: [
    { zone_id: 'estante_superior', name: 'Estante Superior (Nivel Ojos)', level: 'shelf', product_category: 'Snacks y Galletas Premium', window_start_s: 0.0, window_end_s: 300.0, people_count: 42, interaction_count: 23, pick_up_count: 9, put_back_count: 2, average_dwell_time_s: 16.8, interaction_rate: 0.5476, pick_up_rate: 0.3913, conversion_rate: 0.1667 },
    { zone_id: 'estante_inferior', name: 'Estante Inferior (Nivel Suelo)', level: 'shelf', product_category: 'Formatos Familiares Gran Volumen', window_start_s: 0.0, window_end_s: 300.0, people_count: 26, interaction_count: 12, pick_up_count: 3, put_back_count: 2, average_dwell_time_s: 8.4, interaction_rate: 0.4615, pick_up_rate: 0.25, conversion_rate: 0.0384 },
  ],
  video_demo_cabecera: [{ zone_id: 'cabecera_isla', name: 'Isla de Oferta Estacional', level: 'gondola', product_category: null, window_start_s: 0.0, window_end_s: 150.0, people_count: 9, interaction_count: 4, pick_up_count: 0, put_back_count: 0, average_dwell_time_s: 4.12, interaction_rate: null, pick_up_rate: null, conversion_rate: null }],
};
