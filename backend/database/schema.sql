-- ============================================================================
--  GONDOLA INTELIGENTE - esquema de base de datos (PostgreSQL)
-- ============================================================================
--
--  QUIEN ESCRIBE AQUI
--  ------------------
--  SOLO el backend. El AI Service NUNCA toca PostgreSQL: escribe archivos
--  .jsonl y ahi termina su trabajo. Ver docs/architecture.md.
--
--      YOLO -> JSONL -> etapas -> JSONL -> Backend -> PostgreSQL
--
--  PRIVACIDAD POR DISENO
--  ---------------------
--  PROHIBIDA cualquier columna de dato personal: nombre, documento, correo,
--  telefono, rostro, fotografia, biometria o cualquier caracteristica fisica.
--  `track_id` es un numero anonimo y temporal que solo tiene sentido dentro de
--  un video; no identifica a nadie y se reinicia con cada procesamiento.
--
--  Instalacion:
--      psql -U postgres -d gondola -f backend/database/schema.sql
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- para gen_random_uuid()


-- ============================================================================
--  videos : un video procesado
-- ============================================================================
-- PK  id (UUID)  -- generado por la base, estable para siempre
-- UQ  video_id   -- la etiqueta corta del .env ("video_001"), la que viaja en
--                -- los .jsonl. Es unica para poder importar por nombre sin
--                -- tener que conocer el UUID.
CREATE TABLE videos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id        TEXT        NOT NULL UNIQUE,
    source_name     TEXT,                    -- nombre del archivo, sin la ruta
    fps             REAL        NOT NULL CHECK (fps > 0),
    width           INTEGER     NOT NULL CHECK (width  > 0),
    height          INTEGER     NOT NULL CHECK (height > 0),
    frame_count     INTEGER     CHECK (frame_count >= 0),
    duration_s      REAL        CHECK (duration_s >= 0),
    contract_version TEXT       NOT NULL,    -- con que version del contrato se produjo
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  videos IS
    'Un video procesado. No guarda el video ni ningun fotograma: solo sus propiedades.';
COMMENT ON COLUMN videos.video_id IS
    'Etiqueta corta del .env (VIDEO_ID). Es la que aparece en cada linea de los .jsonl.';


-- ============================================================================
--  zones : las zonas de la tienda, con jerarquia
-- ============================================================================
-- PK  id (UUID)
-- FK  parent_id -> zones.id   -- auto-referencia: asi una gondola contiene sus
--                             -- estantes sin necesidad de una segunda tabla.
--
--      gondola_A            (parent_id = NULL,  level = 'gondola')
--        +- estante_1       (parent_id = gondola_A, level = 'shelf')
--        +- estante_2       (parent_id = gondola_A, level = 'shelf')
--
-- ON DELETE CASCADE: borrar una gondola borra sus estantes. Un estante sin
-- gondola no significa nada.
CREATE TABLE zones (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id     TEXT        NOT NULL UNIQUE,   -- 'gondola_A', 'estante_2'
    name        TEXT        NOT NULL,          -- nombre legible para el dashboard
    level       TEXT        NOT NULL CHECK (level IN ('gondola', 'shelf')),
    parent_id   UUID        REFERENCES zones(id) ON DELETE CASCADE,
    product_category TEXT,                     -- 'bebidas', 'snacks'...
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Una gondola no cuelga de nadie; un estante siempre cuelga de una gondola.
    CONSTRAINT jerarquia_coherente CHECK (
        (level = 'gondola' AND parent_id IS NULL) OR
        (level = 'shelf'   AND parent_id IS NOT NULL)
    )
);

CREATE INDEX idx_zones_parent ON zones(parent_id);

COMMENT ON COLUMN zones.parent_id IS
    'Auto-referencia a zones.id. NULL en una gondola; en un estante apunta a su gondola.';


-- ============================================================================
--  events : el evento enriquecido completo, tal como sale del pipeline
-- ============================================================================
-- PK  id (UUID)
-- FK  video_id -> videos.id   ON DELETE CASCADE
--         Borrar un video borra sus eventos. Es nuestra herramienta de
--         borrado de datos: una sola sentencia y no queda rastro.
-- FK  zone_id  -> zones.id    ON DELETE SET NULL
--         Borrar una zona NO debe borrar los eventos: se pierde la
--         clasificacion, no la observacion.
--
-- Esta tabla es el espejo de gondola/contract.py. Si cambia el contrato,
-- cambia aqui, y se sube CONTRACT_VERSION en los dos lados.
CREATE TABLE events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id        UUID        NOT NULL REFERENCES videos(id) ON DELETE CASCADE,

    frame_number    INTEGER     NOT NULL CHECK (frame_number >= 0),
    timestamp_s     REAL        NOT NULL CHECK (timestamp_s >= 0),

    -- track_id: ANONIMO. Enlaza detecciones de la misma silueta dentro de UN
    -- video. No identifica a nadie, no persiste entre videos, y si la misma
    -- persona sale y vuelve a entrar recibe otro numero. Eso es deseado.
    track_id        INTEGER,

    -- Deteccion. width/height son PIXELES DE LA CAJA, no medidas de la
    -- persona: la misma persona da cajas distintas segun lo lejos que este.
    detection_class TEXT        NOT NULL DEFAULT 'person'
                                CHECK (detection_class = 'person'),
    confidence      REAL        NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    bbox_x          REAL        NOT NULL CHECK (bbox_x >= 0),
    bbox_y          REAL        NOT NULL CHECK (bbox_y >= 0),
    bbox_width      REAL        NOT NULL CHECK (bbox_width  > 0),
    bbox_height     REAL        NOT NULL CHECK (bbox_height > 0),

    zone_id         UUID        REFERENCES zones(id) ON DELETE SET NULL,
    segment         TEXT,

    interaction_event TEXT      CHECK (interaction_event IN
                                ('APPROACH', 'PICK_UP', 'PUT_BACK')),
    product_zone    TEXT,

    dwell_time_s    REAL        CHECK (dwell_time_s >= 0),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- El pipeline produce como mucho una fila por (video, frame, track). Si
    -- se reimporta el mismo .jsonl, esto lo impide en vez de duplicar todo.
    CONSTRAINT evento_unico UNIQUE (video_id, frame_number, track_id, bbox_x, bbox_y)
);

CREATE INDEX idx_events_video       ON events(video_id);
CREATE INDEX idx_events_zone        ON events(zone_id);
CREATE INDEX idx_events_track       ON events(video_id, track_id);
CREATE INDEX idx_events_interaction ON events(interaction_event)
    WHERE interaction_event IS NOT NULL;

COMMENT ON COLUMN events.track_id IS
    'Identificador ANONIMO y temporal de seguimiento. No identifica personas.';
COMMENT ON COLUMN events.bbox_width IS
    'Ancho de la caja EN PIXELES. NO es la estatura ni ninguna medida de la persona.';


-- ============================================================================
--  metrics : agregados por video y zona
-- ============================================================================
-- PK  id (UUID)
-- FK  video_id -> videos.id  ON DELETE CASCADE
-- FK  zone_id  -> zones.id   ON DELETE CASCADE
--         Los agregados de una zona borrada no significan nada: se van con ella.
-- UQ  (video_id, zone_id, window_start)
--         Un agregado por video, zona y ventana de tiempo.
CREATE TABLE metrics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    zone_id             UUID NOT NULL REFERENCES zones(id)  ON DELETE CASCADE,

    window_start_s      REAL NOT NULL DEFAULT 0 CHECK (window_start_s >= 0),
    window_end_s        REAL CHECK (window_end_s >= window_start_s),

    -- ¡¡¡ AVISO: EL ERROR MAS CARO QUE PUEDE COMETER ESTE PROYECTO !!!
    -- ------------------------------------------------------------------------
    -- people_count SE CALCULA CONTANDO track_id DISTINTOS, NUNCA FILAS.
    --
    --     CORRECTO:    COUNT(DISTINCT track_id)
    --     CATASTROFE:  COUNT(*)
    --
    -- Una sola persona parada 20 segundos frente a una gondola genera unos 500
    -- eventos (uno por frame). Con COUNT(*) esa persona se convierte en "500
    -- clientes visitaron la gondola A". Las cifras salen infladas cientos de
    -- veces, parecen espectaculares, y toda recomendacion de planograma que se
    -- derive de ellas es basura.
    --
    -- Es un error silencioso: no hay excepcion, no hay test que lo detecte
    -- solo, y el numero se ve "bien" en el dashboard. Reviselo cada vez que
    -- escriba una consulta que cuente personas.
    -- ------------------------------------------------------------------------
    people_count        INTEGER NOT NULL DEFAULT 0 CHECK (people_count >= 0),

    interaction_count   INTEGER NOT NULL DEFAULT 0 CHECK (interaction_count >= 0),
    pick_up_count       INTEGER NOT NULL DEFAULT 0 CHECK (pick_up_count >= 0),
    put_back_count      INTEGER NOT NULL DEFAULT 0 CHECK (put_back_count >= 0),

    average_dwell_time_s REAL CHECK (average_dwell_time_s >= 0),

    -- Tasas. Se guardan calculadas para que el dashboard no las recalcule en
    -- cada carga, pero siempre se derivan de los conteos de arriba.
    interaction_rate    REAL CHECK (interaction_rate BETWEEN 0 AND 1),  -- interacciones / personas
    pick_up_rate        REAL CHECK (pick_up_rate     BETWEEN 0 AND 1),  -- pick_up / interacciones
    conversion_rate     REAL CHECK (conversion_rate  BETWEEN 0 AND 1),  -- pick_up / personas

    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT metrica_unica UNIQUE (video_id, zone_id, window_start_s)
);

CREATE INDEX idx_metrics_video ON metrics(video_id);
CREATE INDEX idx_metrics_zone  ON metrics(zone_id);

COMMENT ON COLUMN metrics.people_count IS
    'Personas DISTINTAS: COUNT(DISTINCT track_id). NUNCA COUNT(*): cada persona genera cientos de eventos.';


-- ============================================================================
--  Consulta de referencia: asi se calcula people_count. Copiela.
-- ============================================================================
-- SELECT
--     e.zone_id,
--     COUNT(DISTINCT e.track_id) AS people_count,        -- <-- DISTINCT
--     COUNT(*) FILTER (WHERE e.interaction_event IS NOT NULL) AS interaction_count,
--     COUNT(*) FILTER (WHERE e.interaction_event = 'PICK_UP')  AS pick_up_count,
--     COUNT(*) FILTER (WHERE e.interaction_event = 'PUT_BACK') AS put_back_count,
--     AVG(e.dwell_time_s)                                AS average_dwell_time_s
-- FROM events e
-- WHERE e.video_id = $1 AND e.track_id IS NOT NULL
-- GROUP BY e.zone_id;
