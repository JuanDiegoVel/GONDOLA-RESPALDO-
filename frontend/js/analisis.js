// Retroalimentacion automatica y exportar a CSV
// Parte del dashboard de Gondola Inteligente. Se carga desde index.html
// como <script> clasico (no modulo ES): ver el comentario de index.html.

// Junta todo lo que un video necesita para renderizarse por completo
// (detalle, metricas de zona, jerarquia, posiciones) en un solo objeto,
// para que renderSummaryCards/renderZonesSection/renderPositionsHeatmap/
// renderZonesHeatmap/renderFeedback puedan dibujar CUALQUIER video -el
// principal o cualquiera de los dos de la comparacion- sin duplicar su
// logica. Sin argumento devuelve el paquete del video principal (mismo
// comportamiento que antes de que existiera la comparacion).
function bundleDe(slot) {
  if (!slot) {
    return {
      videoId: state.selectedVideoId,
      detail: state.videoDetail, isLoadingDetail: state.isLoadingDetail,
      metrics: state.zoneMetrics, isLoadingMetrics: state.isLoadingMetrics, errorMetrics: state.errorMetrics,
      hierarchy: state.zoneHierarchy, isLoadingHierarchy: state.isLoadingHierarchy,
      positions: state.positions, isLoadingPositions: state.isLoadingPositions,
      zonesGeometry: state.zonesGeometry,
      heatmapId: 'positions-heatmap-canvas',
    };
  }
  return {
    videoId: state[`compare${slot}`],
    detail: state[`compare${slot}Detail`], isLoadingDetail: state[`isLoadingCompare${slot}`],
    metrics: state[`compare${slot}Metrics`], isLoadingMetrics: state[`isLoadingCompare${slot}Metrics`], errorMetrics: null,
    hierarchy: state[`compare${slot}Hierarchy`], isLoadingHierarchy: state[`isLoadingCompare${slot}Hierarchy`],
    positions: state[`compare${slot}Positions`], isLoadingPositions: state[`isLoadingCompare${slot}Positions`],
    zonesGeometry: state[`compare${slot}ZonesGeometry`],
    heatmapId: `positions-heatmap-canvas-${slot.toLowerCase()}`,
  };
}

// Logica pura (sin HTML): las mismas reglas simples sobre los numeros ya
// calculados, en un arreglo de {titulo, texto}. Separada de renderFeedback()
// para que el boton de exportar (CSV, ver exportarCSV() mas abajo) pueda
// reutilizar EXACTAMENTE el mismo texto que ve la persona en pantalla, sin
// mantener dos copias del mismo razonamiento.
function generarNotasFeedback(bundle) {
  if (!bundle.detail) return [];
  const d = bundle.detail;
  const zones = bundle.metrics;
  const notas = [];

  if (d.pick_up_count === 0) {
    notas.push({
      titulo: 'Cero tomas de producto detectadas (PICK_UP)',
      texto: d.interaction_count > 0
        ? `Hubo ${formatNumber(d.interaction_count)} acercamiento(s) al estante, pero ninguno se clasificó como una toma real. Puede ser que de verdad nadie se llevó nada, o que el gesto fue muy breve, con las manos ocultas, o quedó justo en el borde del umbral de detección — es una limitación conocida del pipeline, no necesariamente lo que pasó en la tienda.`
        : `La góndola tuvo muy poco o ningún tránsito frente a ella en este clip: sin acercamientos, no hay de dónde sacar una toma.`,
    });
  }

  if (d.pick_up_count > 0 && d.put_back_count === 0) {
    notas.push({
      titulo: 'Tasa de rechazo en 0% — no se mueve porque no hay con qué compararla',
      texto: `Con ${formatNumber(d.pick_up_count)} toma(s) y 0 devoluciones registradas, la fórmula (devoluciones ÷ tomas) siempre da 0%, sin importar cuántas tomas haya. Puede significar que el producto convenció al 100% de quien lo tomó, pero también que el video es muy corto para capturar una devolución, o que PUT_BACK es un gesto más ambiguo de detectar que PICK_UP con el mismo umbral.`,
    });
  } else if (d.pick_up_count === 0) {
    notas.push({
      titulo: 'Tasa de rechazo no calculable (—), no es lo mismo que 0%',
      texto: `Sin ninguna toma detectada no hay denominador: el guion (—) es un dato ausente, no una devolución de "cero por ciento" que sí se pueda comparar contra otro video.`,
    });
  }

  if (d.duration_s && d.duration_s < 180 && d.people_count > 0) {
    notas.push({
      titulo: `Video corto (${formatDuration(d.duration_s)}): las tasas son poco estables`,
      texto: `Con solo ${formatNumber(d.people_count)} persona(s) distinta(s) detectada(s), cada una pesa mucho en el promedio — una sola toma o devolución de más o de menos mueve cualquier porcentaje varios puntos. No lo trates como una muestra representativa, es una demostración puntual del pipeline.`,
    });
  }

  if (bundle.videoId.startsWith('video_demo_merl_') && d.people_count > 4) {
    notas.push({
      titulo: `¿${formatNumber(d.people_count)} personas distintas en un clip pensado para una sola?`,
      texto: `Este video viene del dataset público MERL Shopping Dataset, grabado con un único sujeto por clip. Que el sistema cuente ${formatNumber(d.people_count)} "personas distintas" probablemente significa que el rastreador perdió a esa persona en algún momento (una oclusión, un giro brusco) y la volvió a enganchar como si fuera alguien nuevo, no que hayan pasado ${formatNumber(d.people_count)} personas reales por la cámara. Es una limitación conocida del tracking, ver el bug ya documentado de video_001.`,
    });
  }

  const zonaMuyActiva = zones.find((z) => z.interaction_rate !== null && z.interaction_rate >= 0.9 && (z.people_count || 0) >= 3);
  if (zonaMuyActiva) {
    notas.push({
      titulo: `${zonaMuyActiva.name}: casi todo el que pasa "interactúa" (${formatPercentage(zonaMuyActiva.interaction_rate)})`,
      texto: `Puede ser que el estante de verdad atraiga a casi cualquiera que se acerque, o que el área de piso calibrada (floor_zone en data/zones/) sea tan ancha que capture a quien solo camina cerca, no solo a quien se detiene a mirar. Si este patrón se repite en todos los videos, vale la pena revisar esa calibración antes de confiar en el número.`,
    });
  }

  return notas;
}

function csvEscape(valor) {
  const texto = String(valor ?? '');
  return /[",\n]/.test(texto) ? '"' + texto.replace(/"/g, '""') + '"' : texto;
}

// Descarga un .csv (Excel lo abre directo, sin ningun plugin ni libreria
// nueva) con TODO lo que ve la persona del video elegido: resumen general,
// tabla por zona y las mismas notas de retroalimentacion -reutiliza
// generarNotasFeedback(), el mismo texto que ya se ve en pantalla, para que
// el reporte nunca diga algo distinto de lo que muestra el dashboard.
function exportarCSV() {
  const bundle = bundleDe();
  const d = bundle.detail;
  if (!d) return;
  const current = state.videos.find((v) => v.video_id === bundle.videoId);
  const rejection = calculateRejectionRate(d.put_back_count, d.pick_up_count);
  const filas = [];

  filas.push(['Góndola Inteligente - Reporte']);
  filas.push(['Video', current ? (current.source_name || d.video_id) : d.video_id]);
  filas.push(['video_id', d.video_id]);
  filas.push(['Generado', new Date().toLocaleString('es-CO')]);
  filas.push([]);

  filas.push(['Resumen general']);
  filas.push(['Métrica', 'Valor']);
  filas.push(['Personas detectadas', d.people_count]);
  filas.push(['Interacciones', d.interaction_count]);
  filas.push(['Pick-ups', d.pick_up_count]);
  filas.push(['Put-backs', d.put_back_count]);
  filas.push(['Tasa de rechazo', rejection.label]);
  filas.push(['Permanencia media (s)', d.average_dwell_time_s ?? '']);
  filas.push([]);

  filas.push(['Análisis por zona']);
  filas.push(['Zona', 'Nivel', 'Categoría', 'Personas', 'Interacción %', 'Pick-ups', 'Put-backs', 'Permanencia (s)', 'Conversión %']);
  bundle.metrics.forEach((z) => {
    filas.push([
      z.name,
      z.level === 'gondola' ? 'Góndola' : z.level === 'shelf' ? 'Estante' : 'Zona',
      z.product_category || '',
      z.people_count,
      z.interaction_rate !== null ? Math.round(z.interaction_rate * 100) : '',
      z.pick_up_count,
      z.put_back_count,
      z.average_dwell_time_s ?? '',
      z.conversion_rate !== null ? Math.round(z.conversion_rate * 100) : '',
    ]);
  });
  filas.push([]);

  const notas = generarNotasFeedback(bundle);
  if (notas.length) {
    filas.push(['Retroalimentación']);
    filas.push(['Título', 'Explicación']);
    notas.forEach((n) => filas.push([n.titulo, n.texto]));
  }

  const csv = filas.map((fila) => fila.map(csvEscape).join(',')).join('\r\n');
  // BOM al inicio: sin esto, Excel abre el archivo asumiendo la
  // codificacion del sistema y las tildes/eñes salen mal.
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = `gondola-inteligente_${d.video_id}.csv`;
  document.body.appendChild(enlace);
  enlace.click();
  document.body.removeChild(enlace);
  URL.revokeObjectURL(url);
}
