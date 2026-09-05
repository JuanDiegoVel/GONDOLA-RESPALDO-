# Base de datos

Esquema: [`backend/database/schema.sql`](../backend/database/schema.sql) ·
Datos de ejemplo: [`seed_example.sql`](../backend/database/seed_example.sql)

**PostgreSQL corre en Docker**, con las credenciales y el puerto que ya trae
`backend/.env.example` (`postgresql://gondola:gondola_dev@localhost:5433/gondola`
— el 5433, no el 5432 de siempre, para no chocar con un Postgres que ya
tengas instalado):

```bash
cd backend
docker compose up -d
docker exec -i gondola-postgres psql -U gondola -d gondola < database/schema.sql
docker exec -i gondola-postgres psql -U gondola -d gondola < database/seed_example.sql   # datos ficticios, opcional
```

`docker exec -i ... psql ... < archivo` corre `psql` **dentro** del
contenedor, asi que no hace falta tener PostgreSQL instalado en la maquina
para nada mas que Docker. Si prefieres un Postgres instalado a mano en vez
de Docker, ajusta `DATABASE_URL` en `backend/.env` a como corresponda y usa
`psql`/`createdb` normalmente contra esa instancia.

> **El AI Service nunca escribe aquí.** El pipeline produce archivos `.jsonl`;
> solo el backend los importa a PostgreSQL. El porqué está en
> [architecture.md](architecture.md).

---

## Las cuatro tablas

```
   videos ──────┬──< events >──── zones
                │                   │
                └──< metrics >──────┘
```

| Tabla | Guarda | Una fila es |
|---|---|---|
| `videos` | Videos procesados | Un video |
| `zones` | Góndolas y estantes | Una zona de la tienda |
| `events` | El evento enriquecido completo | **Una persona en un frame** |
| `metrics` | Agregados | Un resumen por video, zona y ventana |

`events` es el espejo de [`contract.py`](../ai-service/gondola/contract.py). Si
cambia el contrato, cambia esta tabla, y se sube `CONTRACT_VERSION` en los dos
lados.

---

## Claves primarias y foráneas

**Todas las claves primarias son UUID** generados por la base
(`gen_random_uuid()`). No se reutilizan, no revelan cuántas filas hay y se
pueden generar sin consultar antes.

`videos.video_id` y `zones.zone_id` son **claves únicas alternativas**: son las
etiquetas de texto que viajan en los `.jsonl` (`"video_001"`, `"gondola_A"`).
El importador busca por ellas y obtiene el UUID; los `.jsonl` nunca contienen
UUID.

| Foránea | Apunta a | Al borrar el padre | Por qué |
|---|---|---|---|
| `zones.parent_id` | `zones.id` | **CASCADE** | Un estante sin su góndola no significa nada. |
| `events.video_id` | `videos.id` | **CASCADE** | Borrar el video borra sus eventos. Es nuestro borrado de datos: una sentencia y no queda rastro. |
| `events.zone_id` | `zones.id` | **SET NULL** | Borrar una zona pierde la clasificación, no la observación. El evento ocurrió igual. |
| `metrics.video_id` | `videos.id` | **CASCADE** | |
| `metrics.zone_id` | `zones.id` | **CASCADE** | Un agregado de una zona borrada no se puede interpretar. |

Que `events.zone_id` sea `SET NULL` y `metrics.zone_id` sea `CASCADE` es
deliberado: un evento es un hecho observado y sobrevive a que se reorganice la
tienda; una métrica es una interpretación y no.

---

## Jerarquía de zonas

`zones` se referencia a sí misma. Una góndola tiene `parent_id = NULL`; un
estante apunta a su góndola.

```
   demo_gondola_A          level='gondola'   parent_id = NULL
     ├── demo_estante_A1   level='shelf'     parent_id = demo_gondola_A
     └── demo_estante_A2   level='shelf'     parent_id = demo_gondola_A
```

Una restricción `CHECK` impide los dos errores posibles: una góndola con padre
y un estante sin él.

Así se pueden dar métricas por góndola completa o por estante concreto, que es
justo lo que necesita un planograma: no basta con "la góndola A funciona", hay
que saber **qué estante**.

---

## ⚠️ `people_count` se cuenta con DISTINCT. Siempre.

```sql
-- CORRECTO
COUNT(DISTINCT track_id) AS people_count

-- CATÁSTROFE
COUNT(*) AS people_count
```

**Este es el error más caro que puede cometer el proyecto.**

Una persona parada 20 segundos frente a una góndola genera unos **500 eventos**,
uno por frame. Con `COUNT(*)`, esa persona se convierte en *"500 clientes
visitaron la góndola A"*.

Lo que lo hace peligroso no es la magnitud del error, es que **es silencioso**:

- No lanza ninguna excepción.
- El dashboard muestra un número grande y creíble.
- Ningún test lo detecta solo: la consulta es sintácticamente correcta.
- Todas las recomendaciones de planograma derivadas de él son basura, pero
  parecen espectaculares.

Cada vez que escribas una consulta que cuente personas, párate y comprueba que
dice `DISTINCT`. Está advertido también dentro del `schema.sql`.

**Consulta de referencia** (cópiala en vez de escribirla de nuevo):

```sql
SELECT
    e.zone_id,
    COUNT(DISTINCT e.track_id)                              AS people_count,
    COUNT(*) FILTER (WHERE e.interaction_event IS NOT NULL)  AS interaction_count,
    COUNT(*) FILTER (WHERE e.interaction_event = 'PICK_UP')  AS pick_up_count,
    COUNT(*) FILTER (WHERE e.interaction_event = 'PUT_BACK') AS put_back_count,
    AVG(e.dwell_time_s)                                      AS average_dwell_time_s
FROM events e
WHERE e.video_id = $1 AND e.track_id IS NOT NULL
GROUP BY e.zone_id;
```

---

## Las métricas y sus tasas

| Columna | Qué significa |
|---|---|
| `people_count` | Personas **distintas** que pasaron por la zona. |
| `interaction_count` | Eventos de interacción (los tres tipos). |
| `pick_up_count` | Productos tomados. |
| `put_back_count` | Productos devueltos. |
| `average_dwell_time_s` | Segundos medios de permanencia. |
| `interaction_rate` | interacciones / personas — *¿la góndola llama la atención?* |
| `pick_up_rate` | pick_up / interacciones — *¿de los que se acercan, cuántos toman?* |
| `conversion_rate` | pick_up / personas — *¿de los que pasan, cuántos toman?* |

Un `put_back_count` alto junto a un `pick_up_count` alto es una señal
interesante: el producto atrae, pero algo (el precio, el envase) hace que se
devuelva.

---

## Privacidad: qué NO hay aquí

**Prohibida cualquier columna de dato personal**: nombre, documento, correo,
teléfono, rostro, fotografía, huella, biometría o características físicas.

`track_id` es un **entero anónimo y temporal**. Solo dice "esta caja y aquella
son la misma silueta dentro de este video". Se reinicia con cada procesamiento
y no corresponde a ninguna persona real: si alguien sale y vuelve a entrar,
recibe otro número, y eso está bien — no queremos reconocerlo.

`bbox_width` y `bbox_height` son **píxeles de la caja**, no la estatura ni la
contextura de nadie. La misma persona da cajas distintas según lo lejos que
esté de la cámara.

La base no almacena imágenes ni fotogramas. Detalle completo en
[privacy.md](privacy.md).
