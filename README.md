# Caso Expreso · Puente LogiSur → Expreso Andino

Programa en Python que toma el export diario de remitos de LogiSur, se queda con los que viajan por Expreso Andino, los transforma al formato de su API y los carga, dejando un resumen de la corrida para el equipo de operaciones. Se puede volver a correr sin duplicar envíos.

Resultado con los datos del challenge (ver [`ejemplo_corrida/`](ejemplo_corrida/)):

| | Cantidad |
| --- | ---: |
| Remitos en el export | 51 |
| De Expreso Andino (sin contar un repetido) | 23 |
| Cargados | 19 |
| Ya estaban cargados de antes | 1 |
| Rechazados por datos incompletos | 3 |
| Errores técnicos | 0 |
| Atrasados al 03/10/2026 (opcional) | 2 |

## Cómo correrlo

Requisitos: Python 3.9 o superior.

```bash
# 1. Crear el entorno virtual e instalar dependencias
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux / macOS
pip install -r requirements.txt

# 2. Levantar la API de prueba (en otra terminal, y dejarla abierta)
python kit/expreso_api.py

# 3. Correr el puente
python -m expreso_bridge.main data/remitos_2026-09-30.json

# Opcional: además, listar los envíos atrasados a una fecha
python -m expreso_bridge.main data/remitos_2026-09-30.json --atrasados --hoy 2026-10-03

# Tests
python -m pytest -v
```

Cada corrida crea una carpeta `output/corrida_AAAAMMDD_HHMMSS/` con:

- `resumen.md`: cuántos se cargaron, cuáles no y por qué, y observaciones del export.
- `detalle.csv`: una fila por remito con su resultado y `tracking_id`. Usa `;` como separador y UTF-8 con BOM para que Excel en español lo abra con las columnas y las tildes bien.
- `atrasados.csv`: solo con `--atrasados`.

La URL y la API key se toman de las variables de entorno `EXPRESO_API_URL` y `EXPRESO_API_KEY`. Si no están definidas, se usan las del entorno de prueba.

El programa termina con código `0` si todo se procesó, `1` si quedaron errores técnicos para reintentar y `2` si no pudo correr (API caída, API key inválida, export ilegible). Los remitos rechazados por datos no son una falla del programa: quedan en el resumen para que operaciones los corrija.

## Cómo funciona

```
export JSON ──► loader ──► transform ──► client ──► API Expreso Andino
                  │            │            │
                  └────────────┴────────────┴──► report (resumen.md + detalle.csv)
```

| Módulo | Responsabilidad |
| --- | --- |
| `loader.py` | Lee el export, filtra los remitos de Expreso Andino y detecta repetidos. |
| `transform.py` | Convierte cada remito al formato de la API y valida los datos. |
| `client.py` | Habla con la API: reintentos, manejo de duplicados y errores. |
| `report.py` | Genera el resumen para operaciones. |
| `atrasados.py` | Opcional: consulta estados y lista los envíos atrasados. |
| `main.py` | Orquesta el proceso y maneja la línea de comandos. |

## Lo que encontré en los datos y cómo lo resolví

- **El transportista viene escrito de cinco formas**: `EXPRESO ANDINO`, `Expreso Andino`, `EXPRESO ANDINO ` (con espacio), `expreso andino` y `Exp. Andino`. Se normaliza (minúsculas, espacios) y se compara contra una lista cerrada de alias. Elegí una lista explícita en vez de algo como "contiene *andino*" para no mandarle a Expreso Andino envíos de otra empresa con un nombre parecido: prefiero que un remito quede afuera y se note en el resumen (que incluye el conteo por transportista) a que se cargue en el transporte equivocado.
- **Peso como texto con coma decimal** (`"145,1"`). Se acepta tanto número como texto en formato argentino, incluido `"1.234,5"`.
- **Provincias que la API no acepta**: `Tucuman`, `Neuquen`, `BA`, `Bs. As.`, `Cba`, `CABA`, `Capital Federal`. Primero se compara ignorando tildes, mayúsculas y puntos; las abreviaturas se resuelven con una tabla de alias. La lista de provincias válidas se pide a la API (`GET /v1/provinces`) en cada corrida, así la fuente de verdad es el propio expreso.
- **Servicio en castellano**: `NORMAL` → `standard`, `URGENTE` → `express`.
- **Un remito repetido en el export** (R-10000507, idéntico las dos veces): se carga una sola vez y se informa.
- **Datos imposibles de corregir**: un remito sin código postal, uno con dirección en blanco y uno con 0 bultos. No se cargan y quedan en el resumen con el motivo.

## Manejo de la API

| Respuesta | Qué hace el programa |
| --- | --- |
| `201` | Cargado. |
| `409` en el primer intento | Ya estaba cargado de antes: se informa como tal, con su `tracking_id`. No es un error. |
| `422` | Rechazado, con el detalle de la API. No se reintenta: mandar lo mismo daría el mismo error. |
| `500`, `502`, `503`, `504`, timeout o sin conexión | Se reintenta hasta 4 veces con espera creciente (0,5 s, 1 s, 2 s). |
| `409` después de un reintento | El intento anterior falló al responder pero sí creó el envío: se cuenta como cargado. |
| Se agotan los reintentos | Antes de declararlo fallido se consulta `GET /v1/shipments?external_ref=...` por si alguno de los intentos lo creó. |
| `401` | Se corta la corrida: con la API key mal, fallarían todos. |

El punto delicado es que un `500` o un timeout **no garantizan que el envío no se haya creado**. Por eso un reintento que recibe `409` se interpreta como éxito, y por eso la consulta final antes de dar algo por perdido.

**Re-ejecución sin duplicados:** la API garantiza que `external_ref` es único, así que la fuente de verdad sobre qué está cargado es la propia API. Si se vuelve a correr el mismo export, cada envío ya cargado responde `409` y se informa como "ya estaba cargado". No uso un registro local de lo enviado porque podría desincronizarse de la API (por ejemplo, si se borra o si el programa corre desde otra máquina). En `ejemplo_corrida/segunda_corrida/` está el resumen de correr el mismo export dos veces: 0 cargados y 20 que ya existían.

## Supuestos

- `BA` y `Bs. As.` se interpretan como **provincia** de Buenos Aires, no como Capital. En el export siempre acompañan localidades del interior (Pilar, Mar del Plata).
- Si un dato obligatorio falta o es inválido, **no se completa ni se adivina** (por ejemplo, el código postal a partir de la localidad). Un envío con datos inventados puede terminar mal entregado o mal asegurado; es preferible rechazarlo y que operaciones lo corrija en el sistema de origen.
- Si un remito apareciera repetido **con datos distintos**, no se carga ninguna versión, porque no hay forma de saber cuál es la correcta. No ocurre en este export, pero está contemplado y testeado.
- Los campos que la API no tiene (`volumen_m3`, `cliente`, `fecha_remito`, `observaciones`) se descartan. El teléfono vacío no se envía, porque es opcional.
- Para los atrasados se toma "hoy" = 03/10/2026, como pide el enunciado. Un envío que vence hoy no se considera atrasado. Los envíos en estado `EXCEPTION` cuentan como no entregados, pero solo son atrasados si su fecha estimada ya pasó.
- Leí el código de la API de prueba para entender qué escenarios simula (duplicado previo, `503` transitorios, un `500` que igual crea el envío). El programa no tiene ninguna referencia hardcodeada: reacciona a los códigos de respuesta documentados en `API.md`.

## Qué cambiaría para usarlo en producción todos los días

- **Programarlo y avisar**: correrlo con el programador de tareas de Windows o cron después de que se genera el export, y usar el código de salida para alertar. Mandar el `resumen.md` por mail o Slack al equipo de operaciones, en lugar de que tengan que ir a buscarlo.
- **Logs en archivo** en lugar de `print`, con fecha, nivel y retención, para poder auditar qué pasó en una corrida de hace semanas.
- **Configuración fuera del código**: sacar el valor por defecto de la API key (que hoy existe para que el challenge corra sin configurar nada) y leerla de un gestor de secretos. Pasar las tablas de alias de transportistas y provincias a un archivo de configuración que operaciones pueda mantener, y alertar cuando aparece un transportista desconocido.
- **Evitar dos corridas simultáneas** con un archivo de bloqueo. La API no duplicaría envíos, pero los dos resúmenes serían confusos.
- **Cortar antes si la API está caída**: hoy cada remito agota sus reintentos por separado. Si fallan varios seguidos, conviene frenar la corrida (patrón *circuit breaker*) y reintentar más tarde. También respetar el header `Retry-After` si la API lo envía, y agregar variación aleatoria a las esperas.
- **Devolver los `tracking_id` a LogiSur**: guardarlos en su sistema o en una base de datos para tener el historial de cada remito y poder seguirlo sin depender de los CSV.
- **Validar la estructura del export** al leerlo (por ejemplo con `pydantic`), para detectar enseguida si el sistema de LogiSur cambia el formato.
- **Reportar las excepciones aparte**: envíos en `EXCEPTION` que todavía no vencieron (por ejemplo R-10000527 y R-10000572) no son "atrasados" según la definición, pero probablemente operaciones quiera enterarse antes.
- **Integración continua**: correr los tests automáticamente en cada push con GitHub Actions.
- **Confirmar con LogiSur** los supuestos de arriba, en especial qué hacer con los remitos incompletos y si `BA` siempre significa provincia.

## Estructura del repositorio

```
├── data/remitos_2026-09-30.json   export del día (entrada)
├── kit/                           API de prueba y su documentación (del challenge)
├── expreso_bridge/                código del puente
├── tests/                         tests (pytest)
├── ejemplo_corrida/               resumen de una corrida real contra la API de prueba
└── requirements.txt
```

## Uso de IA

Usé Claude como asistente durante el desarrollo: para analizar los datos, discutir alternativas de diseño y generar una primera versión del código y los tests. Transcribí el código a mano para entenderlo, corregí los errores que fueron apareciendo, lo probé contra la API de prueba y revisé cada decisión de las que se describen arriba.