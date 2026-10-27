# Plataforma de Análisis Sísmico (Arquitectura Medallón)

Plataforma integral de ingeniería y análisis de datos para la ingesta, validación, procesamiento analítico distribuido y visualización en tiempo real de eventos sísmicos a partir de la API pública del USGS (*United States Geological Survey*).

---

## 1. Arquitectura del Sistema

El sistema implementa una arquitectura medallón basada en tres capas en PostgreSQL 16, orquestadas por Apache Airflow y procesadas exclusivamente con Apache Spark (PySpark):

```mermaid
flowchart TD
    USGS["API Pública USGS<br/>(GeoJSON)"] -->|Extracción Incremental| INGEST["Servicio Ingesta Python<br/>(src.ingestion.service)"]
    INGEST -->|Append-Only JSONB| BRONZE[("PostgreSQL: Capa Bronze<br/>(bronze.earthquakes)")]

    subgraph Airflow["Contenedor Airflow (Java 17 + PySpark)"]
        DAG["DAG usgs_seismic_pipeline<br/>(cada 15 min)"]
        DAG --> T1["Task: extract_and_load_bronze"]
        DAG --> T2["Task: spark_bronze_to_silver"]
        DAG --> T3["Task: spark_silver_to_gold"]
        DAG --> T4["Task: check_data_quality"]
        DAG --> T5["Task: notify_pipeline_availability"]
    end

    BRONZE -->|JDBC Read| T2
    T2 -->|Validación & Deduplicación| SILVER[("PostgreSQL: Capa Silver<br/>(silver.earthquakes)")]
    T2 -->|Métricas de Calidad| METRICS[("metrics.data_quality")]

    SILVER -->|JDBC Read| T3
    T3 -->|Agregaciones Horarias & Rankings| GOLD[("PostgreSQL: Capa Gold<br/>(gold.*)")]

    GOLD -->|ai_reader (Solo Lectura)| AI_MOD["Módulo IA Local<br/>(Ollama llama3.2:1b + Fallback)"]
    AI_MOD --> OPS[("ops.anomaly_alerts & ai_executions")]

    GOLD -->|ai_reader (Herramientas Analíticas)| CHAT["Agente IA Conversacional<br/>(Herramientas + RAG + Verificación)"]
    DOCS[("Documentación Técnica<br/>(docs/*.md)")] -->|RAG BM25| CHAT
    CHAT --> TRACES[("ops.ai_agent_traces")]
    CHAT -->|Inferencia / Fallback| AI_MOD
    AI_MOD -->|Respuesta Validada| CHAT

    GOLD -->|api_reader (Solo Lectura)| API["FastAPI Backend<br/>(Puerto 8000)"]
    CHAT --> API
    T5 -.->|Notificación SSE| API
    API -->|REST + SSE| DASHBOARD["Dashboard Web React<br/>(Leaflet + Chatbot + Tailwind, Puerto 3000)"]
```

> [!IMPORTANT]
> **Procesamiento Real con Spark:** Todo el cálculo analítico y normalización (Bronze → Silver → Gold) se ejecuta en Apache Spark real. Está prohibido el uso de `pandas`, `polars` o `dask`.

---

## 2. Requisitos Previos

- **Sistema Operativo**: Linux / macOS / Windows con WSL2.
- **Docker y Docker Compose**: Docker Engine >= 24.0, Compose v2.
- **Hardware Recomendado**:
  - Memoria RAM: Mínimo 8 GB (16 GB recomendado para correr el stack completo con OpenMetadata).
  - CPU: 4 núcleos lógicos o superior.
- **Puertos Disponibles**:
  - `5433` (o `5432`): PostgreSQL
  - `8000`: Backend FastAPI
  - `8080`: Airflow Webserver
  - `3000`: Dashboard Web React
  - `11434`: Ollama Server
  - `8585`: OpenMetadata Server (perfil `metadata`)

---

## 3. Instalación y Despliegue desde Cero

### Paso 1: Clonar y configurar variables de entorno
```bash
git clone <url-del-repositorio> prueba_final
cd prueba_final
cp .env.example .env
```

### Paso 2: Despliegue por Perfiles con Docker Compose

La plataforma utiliza **perfiles de Compose** para modular el uso de recursos:

1. **Stack Central (`core`)**: Base de datos, Airflow (Webserver + Scheduler), API FastAPI y Frontend React:
   ```bash
   docker compose up -d
   ```
2. **Stack con Inteligencia Artificial (`core` + `ai`)**: Incluye el contenedor de Ollama y la descarga automática del modelo liviano `llama3.2:1b` (<= 3B parámetros):
   ```bash
   docker compose --profile ai up -d
   ```
3. **Stack Completo con Catálogo de Datos (`core` + `ai` + `metadata`)**: Incluye OpenMetadata y Elasticsearch:
   ```bash
   docker compose --profile ai --profile metadata up -d
   ```

### Paso 3: Verificación de Contenedores Activos
```bash
docker compose ps
```
Todos los contenedores deben reportar estado `Up` o `healthy`.

---

## 4. Ejecución del Pipeline y Comandos Manuales

### Interfaz Web de Airflow
- Accede a [http://localhost:8080](http://localhost:8080) (Usuario: `airflow`, Contraseña: `airflow`).
- Los DAGs disponibles son:
  - `usgs_seismic_pipeline`: Pipeline continuo cada 15 minutos (Bronze → Silver → Gold → SSE).
  - `seismic_anomaly_detection`: Detección estadística Z-Score de frecuencias sísmicas horarias inusuales.
  - `daily_seismic_executive_report`: Reporte narrativo ejecutivo de actividad sísmica en las últimas 24 horas.

### Ejecución Manual desde la Terminal (CLI)
Si deseas ejecutar los módulos directamente sin esperar la programación de Airflow:

```bash
# 1. Ingesta desde USGS hacia Bronze
python -m src.ingestion.service

# 2. Procesamiento Bronze -> Silver (Spark)
python -m src.processing.bronze_to_silver

# 3. Procesamiento Silver -> Gold (Spark)
python -m src.processing.silver_to_gold

# 4. Detección de Anomalías Z-Score e Inferencia IA
python -m src.ai.anomaly_detector

# 5. Reporte Ejecutivo Diario
python -m src.ai.daily_report

# 6. Evaluación Cuantitativa del Agente Conversacional (Benchmark de 41 casos)
python -m src.ai.eval.runner
```

---

## 5. Endpoints de la API FastAPI

El backend expone endpoints analíticos validados con Pydantic y documentados interactivamente en [http://localhost:8000/docs](http://localhost:8000/docs).

| Método | Ruta | Descripción |
| :---: | :--- | :--- |
| `GET` | `/health` | Estado del backend y conectividad con PostgreSQL. |
| `GET` | `/api/v1/indicators` | Indicadores de 24h (total eventos, magnitud máx/promedio, alertas de tsunami, puntaje de calidad). |
| `GET` | `/api/v1/events/timeseries` | Serie temporal de sismos agrupados por intervalos horarios. |
| `GET` | `/api/v1/events/distribution` | Conteo de eventos agrupados por rangos de magnitud. |
| `GET` | `/api/v1/rankings/regions` | Top regiones con mayor actividad sísmica en las últimas 24h. |
| `GET` | `/api/v1/events/map` | Coordenadas y atributos para el mapa interactivo (filtros: `start_date`, `end_date`, `min_magnitude`, `region`, `limit`). |
| `GET` | `/api/v1/quality/summary` | Última evaluación de calidad de datos y porcentaje de cumplimiento. |
| `GET` | `/api/v1/alerts/anomalies` | Alertas estadísticas Z-Score detectadas y explicadas. |
| `GET` | `/api/v1/pipeline/status` | Última disponibilidad confirmada del pipeline de datos. |
| `POST` | `/api/v1/ai/chat` | **Agente Conversacional**: Interacción multi-turno con herramientas sobre Gold, RAG documental y fallback determinista. |
| `GET` | `/api/v1/ai/reports` | Listado de reportes ejecutivos y auditorías narrativas generadas por IA local. |
| `GET` | `/api/v1/events/live-stream` | **Flujo SSE**: Notificaciones en tiempo real al finalizar lotes exitosos. |

### Ejemplos con `curl`
```bash
# Consultar al agente de IA conversacional
curl -s -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Cuál fue el sismo de mayor magnitud en las últimas 24 horas?"}' | jq .

# Consultar indicadores globales
curl -s http://localhost:8000/api/v1/indicators | jq .

# Consultar sismos para el mapa con magnitud >= 4.0
curl -s "http://localhost:8000/api/v1/events/map?min_magnitude=4.0&limit=50" | jq .

# Conectarse al flujo SSE
curl -N http://localhost:8000/api/v1/events/live-stream
```

---

## 6. Dashboard Web Interactivo

Disponible en [http://localhost:3000](http://localhost:3000):
- **Tarjetas de KPI**: Eventos 24h, Magnitud Máxima, Magnitud Promedio, Alertas de Tsunami, Puntaje de Calidad y Timestamp de última actualización.
- **Gráficos Dinámicos**: Serie temporal por hora, distribución por intervalos de magnitud y ranking regional.
- **Mapa Leaflet**: Visualización geoespacial con círculos proporcionales a la magnitud y popups con detalles del evento (profundidad, magnitud, fecha UTC).
- **Filtros Unificados**: Fecha inicial, fecha final, magnitud mínima y filtro por región sísmica.
- **Chatbot Inteligente Integrado**: Cajón deslizable (*drawer*) accesible desde el botón "Asistente IA" en la barra de navegación. Ofrece conversación multi-turno, sugerencias de preguntas rápidas, indicación visual de modelo (`llama3.2:1b` o `fallback determinista`), herramientas empleadas y latencia en milisegundos.
- **Actualización Automática**: El canal SSE actualiza los datos en pantalla instantáneamente al completarse un nuevo lote sin necesidad de recargar la página.

---

## 7. Módulo de IA Local, Agente Conversacional y Fallback

La plataforma incorpora capacidades analíticas y conversacionales basadas en el modelo local `llama3.2:1b` (<= 3B parámetros) orquestado con Ollama:

1. **Automatizaciones por Lotes (Batch)**:
   - **Detección de anomalías Z-Score**: Genera explicaciones estadísticas en lenguaje natural validadas con Pydantic (`AnomalyStructuredOutput`).
   - **Reporte ejecutivo diario**: Consolida la actividad de las últimas 24 horas en un informe estructurado (`DailyReportStructuredOutput`).
2. **Agente Conversacional con Herramientas y RAG**:
   - **Clasificador de intención**: Identifica si la consulta es sobre sismos, documentación de arquitectura, ambigua o fuera de dominio. Rechaza consultas ajenas y solicitudes de manipulación de instrucciones (jailbreaks) de inmediato.
   - **Ejecución de herramientas tipadas**: Consulta exclusivamente PostgreSQL Gold bajo el rol de solo lectura `ai_reader` (`get_strongest_earthquake`, `get_earthquake_statistics`, `get_latest_earthquakes`, `compare_earthquake_periods`, `get_magnitude_distribution`, `get_anomaly_alerts`, `get_data_quality_metrics`).
   - **RAG sobre documentación técnica**: Búsqueda en los documentos del proyecto con citas de fuente automáticas (`search_project_documentation`).
   - **Memoria de contexto**: Extrae filtros y regiones de turnos previos para responder preguntas de seguimiento (ej. "¿Y cuántos superaron magnitud 4?").
   - **Verificación Anti-Alucinación y Política de No-Predicción**: Valida matemáticamente que las cifras coincidan con los datos calculados e impone la advertencia científica de que **los sismos no se pueden predecir**.
   - **Fallback Determinista**: Si Ollama no está disponible o excede el timeout (45s), el agente responde de forma inmediata utilizando síntesis determinista verificada sin interrumpir el servicio.
   - **Observabilidad**: Cada consulta, intención, herramientas ejecutadas, latencia y modo de generación se auditan en `ops.ai_agent_traces`.
3. **Framework de Evaluación Cuantitativa**:
   - Dataset reproducible de 41 casos de referencia distribuidos en 12 categorías en [`src/ai/eval/`](file:///home/cohorte-5/Escritorio/prueba_final/src/ai/eval/).
   - Mide exactitud de intención, selección de herramientas, tasa de rechazo fuera de dominio y latencia media (`python -m src.ai.eval.runner`).

---

## 8. Gobernanza y Catálogo con OpenMetadata

- Acceso a la interfaz: [http://localhost:8585](http://localhost:8585).
- Credenciales iniciales: Usuario `admin@openmetadata.org` / Contraseña `admin`.
- **Clasificaciones Medallón**: Los activos están etiquetados como `Medallion.Bronze`, `Medallion.Silver` y `Medallion.Gold`.
- **Linaje de Datos**: Visualización del linaje desde la API del USGS pasando por Bronze, Silver y Gold hasta las alertas analíticas de Ops.

Para sincronizar manualmente el catálogo:
```bash
python -m src.metadata.service
```

---

## 9. Solución a Problemas Frecuentes

### 1. Puerto `5432` ocupado en el host
- *Causa*: Existe una instancia nativa de PostgreSQL corriendo en la máquina anfitriona.
- *Solución*: La plataforma mapea el puerto externo a `5433` por defecto (`POSTGRES_HOST_PORT=5433`). Configura tus herramientas locales para conectar a `localhost:5433`.

### 2. Error de Classpath de JDBC en PySpark
- *Causa*: El archivo `postgresql-42.7.3.jar` no se encuentra en la ruta esperada.
- *Solución*: Ejecuta `python src/processing/verify_spark_jdbc.py`. Si falta el archivo JAR, descárgalo automáticamente ejecutando:
  ```bash
  curl -Lo jars/postgresql-42.7.3.jar https://jdbc.postgresql.org/download/postgresql-42.7.3.jar
  ```

### 3. Timeout o lentitud en inferencia de Ollama
- *Causa*: El modelo corre en CPU en equipos con recursos limitados.
- *Solución*: El timeout está configurado en 45s (`AI_TIMEOUT_SECONDS=45`). Si se agota, el sistema utiliza de forma transparente el fallback determinista garantizando que el pipeline nunca falle.

---

## 10. Suite de Pruebas Automatizadas

La plataforma cuenta con 109 pruebas unitarias y de integración que verifican la arquitectura completa:

```bash
pytest
```

Para ejecutar pruebas específicas por módulo:
```bash
# API y endpoints HTTP
pytest tests/test_api.py -v

# Entorno Spark y transformaciones Medallón (real)
pytest tests/test_spark_environment.py tests/test_bronze_to_silver.py tests/test_silver_to_gold.py -v

# Agente conversacional, orquestación de herramientas y RAG
pytest tests/test_ai_agent_orchestrator.py tests/test_ai_chat.py -v

# Inferencia Ollama, validación Pydantic y fallbacks deterministas
pytest tests/test_ai_deterministic.py tests/test_ai_ollama_integration.py -v

# Dataset de evaluación y benchmark cuantitativo del agente
pytest tests/test_ai_evaluation_suite.py -v

# Catálogo y linaje con OpenMetadata
pytest tests/test_metadata_openmetadata.py -v
```
