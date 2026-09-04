-- ============================================================================
--  DATOS FICTICIOS DE EJEMPLO
-- ============================================================================
--
--  PARA QUE SIRVE ESTO
--  -------------------
--  Para que la Persona 7 (dashboard) pueda trabajar DESDE EL PRIMER DIA, sin
--  esperar a que el pipeline este terminado. Carga esto y ya tiene datos con
--  la forma exacta que tendran los reales.
--
--      psql -U postgres -d gondola -f backend/database/schema.sql
--      psql -U postgres -d gondola -f backend/database/seed_example.sql
--
--  ESTOS DATOS SON INVENTADOS
--  --------------------------
--  Ninguna cifra de aqui sale de procesar un video. Estan puestas a mano para
--  que el dashboard tenga algo que dibujar. NO se pueden usar en una
--  presentacion, ni en un informe, ni citarse como resultado.
--
--  Las personas son ficticias y anonimas: solo hay track_id, que son numeros.
-- ============================================================================

BEGIN;

-- Limpiar antes de recargar. El CASCADE del esquema arrastra events y metrics.
DELETE FROM videos WHERE video_id IN ('video_demo_001', 'video_demo_002');
DELETE FROM zones  WHERE zone_id LIKE 'demo_%';

-- ---------------------------------------------------------------------------
-- Videos
-- ---------------------------------------------------------------------------
INSERT INTO videos (id, video_id, source_name, fps, width, height, frame_count,
                    duration_s, contract_version)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'video_demo_001', 'demo_manana.mp4',
   25.0, 1280, 720, 15000, 600.0, '1.0.0'),
  ('11111111-1111-1111-1111-111111111112', 'video_demo_002', 'demo_tarde.mp4',
   25.0, 1280, 720,  9000, 360.0, '1.0.0');

-- ---------------------------------------------------------------------------
-- Zonas: dos gondolas, cada una con dos estantes.
-- Observa el parent_id: los estantes cuelgan de su gondola.
-- ---------------------------------------------------------------------------
INSERT INTO zones (id, zone_id, name, level, parent_id, product_category)
VALUES
  ('22222222-0000-0000-0000-00000000000a', 'demo_gondola_A', 'Gondola A - Bebidas',
   'gondola', NULL, 'bebidas'),
  ('22222222-0000-0000-0000-00000000000b', 'demo_gondola_B', 'Gondola B - Snacks',
   'gondola', NULL, 'snacks'),

  ('22222222-0000-0000-0000-0000000000a1', 'demo_estante_A1', 'Gondola A - estante 1 (arriba)',
   'shelf', '22222222-0000-0000-0000-00000000000a', 'bebidas'),
  ('22222222-0000-0000-0000-0000000000a2', 'demo_estante_A2', 'Gondola A - estante 2 (altura de ojos)',
   'shelf', '22222222-0000-0000-0000-00000000000a', 'bebidas'),
  ('22222222-0000-0000-0000-0000000000b1', 'demo_estante_B1', 'Gondola B - estante 1',
   'shelf', '22222222-0000-0000-0000-00000000000b', 'snacks');

-- ---------------------------------------------------------------------------
-- Eventos
--
-- OJO A LA FORMA DE ESTOS DATOS: hay pocas personas (track_id 1, 2 y 3) pero
-- MUCHAS filas por persona, porque cada persona aparece en muchos frames.
-- Eso es exactamente lo que pasara con los datos reales, y es la razon por la
-- que people_count se calcula con COUNT(DISTINCT track_id) y nunca COUNT(*).
--
-- Aqui: 8 filas, pero solo 3 personas.
-- ---------------------------------------------------------------------------
INSERT INTO events (video_id, frame_number, timestamp_s, track_id,
                    confidence, bbox_x, bbox_y, bbox_width, bbox_height,
                    zone_id, segment, interaction_event, product_zone, dwell_time_s)
VALUES
  -- Persona 1: se acerca a la gondola A y toma un producto.
  ('11111111-1111-1111-1111-111111111111', 250, 10.00, 1, 0.94, 420, 180, 110, 320,
   '22222222-0000-0000-0000-0000000000a2', 'estante_2', 'APPROACH', 'bebidas',  1.2),
  ('11111111-1111-1111-1111-111111111111', 300, 12.00, 1, 0.92, 425, 182, 108, 318,
   '22222222-0000-0000-0000-0000000000a2', 'estante_2', NULL,       NULL,       3.2),
  ('11111111-1111-1111-1111-111111111111', 355, 14.20, 1, 0.95, 430, 180, 112, 322,
   '22222222-0000-0000-0000-0000000000a2', 'estante_2', 'PICK_UP',  'bebidas',  5.4),
  ('11111111-1111-1111-1111-111111111111', 400, 16.00, 1, 0.91, 450, 185, 110, 315,
   '22222222-0000-0000-0000-0000000000a2', 'estante_2', NULL,       NULL,       7.2),

  -- Persona 2: se acerca, mira, toma y devuelve. No se lleva nada.
  ('11111111-1111-1111-1111-111111111111', 780, 31.20, 2, 0.89, 610, 200, 105, 300,
   '22222222-0000-0000-0000-0000000000a1', 'estante_1', 'APPROACH', 'bebidas',  0.8),
  ('11111111-1111-1111-1111-111111111111', 845, 33.80, 2, 0.93, 615, 198, 106, 305,
   '22222222-0000-0000-0000-0000000000a1', 'estante_1', 'PICK_UP',  'bebidas',  3.4),
  ('11111111-1111-1111-1111-111111111111', 878, 35.10, 2, 0.90, 618, 199, 104, 303,
   '22222222-0000-0000-0000-0000000000a1', 'estante_1', 'PUT_BACK', 'bebidas',  4.7),

  -- Persona 3: pasa por la gondola B y no interactua con nada.
  ('11111111-1111-1111-1111-111111111111', 1450, 58.00, 3, 0.87, 200, 210, 100, 290,
   '22222222-0000-0000-0000-0000000000b1', 'estante_1', 'APPROACH', 'snacks',   0.5);

-- ---------------------------------------------------------------------------
-- Metricas agregadas
--
-- Gondola A: 2 personas distintas (track 1 y 2) en 7 filas de eventos.
--     people_count      = 2     <-- COUNT(DISTINCT track_id), NO las 7 filas
--     interaction_count = 5     2 APPROACH + 2 PICK_UP + 1 PUT_BACK
--     pick_up_count     = 2
--     put_back_count    = 1
--     average_dwell     = 3.70  media de los 7 dwell_time_s de arriba
--     interaction_rate  = 1.00  5 interacciones / 2 personas = 2.5, acotado a 1
--     pick_up_rate      = 0.40  2 pick_up / 5 interacciones
--     conversion_rate   = 1.00  las 2 personas tomaron algo
--
-- Las cifras del PRIMER video salen de los eventos de arriba: se reproducen
-- con la consulta de referencia del final de schema.sql. Las del segundo
-- video estan puestas a mano, no hay eventos que las respalden.
-- ---------------------------------------------------------------------------
INSERT INTO metrics (video_id, zone_id, window_start_s, window_end_s,
                     people_count, interaction_count, pick_up_count, put_back_count,
                     average_dwell_time_s, interaction_rate, pick_up_rate, conversion_rate)
VALUES
  ('11111111-1111-1111-1111-111111111111', '22222222-0000-0000-0000-00000000000a',
   0, 600, 2, 5, 2, 1, 3.70, 1.00, 0.40, 1.00),

  ('11111111-1111-1111-1111-111111111111', '22222222-0000-0000-0000-00000000000b',
   0, 600, 1, 1, 0, 0, 0.50, 1.00, 0.00, 0.00),

  -- Segundo video, para que el dashboard pueda comparar dos periodos.
  ('11111111-1111-1111-1111-111111111112', '22222222-0000-0000-0000-00000000000a',
   0, 360, 5, 9, 4, 2, 6.10, 1.00, 0.44, 0.80),
  ('11111111-1111-1111-1111-111111111112', '22222222-0000-0000-0000-00000000000b',
   0, 360, 3, 4, 1, 0, 2.75, 1.00, 0.25, 0.33);

COMMIT;

-- ============================================================================
--  Comprobacion: el DISTINCT importa. Corre esto despues de cargar.
-- ============================================================================
--
--   SELECT
--       COUNT(*)                   AS filas,          -- da 8
--       COUNT(DISTINCT track_id)   AS personas        -- da 3   <-- este
--   FROM events
--   WHERE video_id = '11111111-1111-1111-1111-111111111111';
--
--  Con 8 filas y 3 personas la diferencia parece pequena. En un video real son
--  50.000 filas y 40 personas. Ahi es donde el error deja de ser un detalle.
