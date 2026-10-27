# Plataforma de Análisis Sísmico (Arquitectura Medallón)

Plataforma de ingeniería de datos para la ingesta, validación, procesamiento analítico y visualización en tiempo real de eventos sísmicos a partir de la API pública del USGS (United States Geological Survey).

## Arquitectura

El sistema implementa una arquitectura medallón basada en tres capas en PostgreSQL, orquestadas por Apache Airflow y procesadas exclusivamente con Apache Spark (PySpark):

- **Bronze**: Datos originales en bruto, append-only, almacenados en JSONB.
- **Silver**: Eventos deduplicados, tipados y validados. Los registros que no cumplen las reglas de calidad son descartados de la memoria y registrados en tablas de métricas operativas.
- **Gold**: Vistas y tablas analíticas agregadas (métricas horarias, ranking de regiones, distribución por magnitud) para el consumo de FastAPI, el dashboard interactivo y el módulo de IA local.

> [!IMPORTANT]
> **Regla estricta:** Todo el procesamiento analítico se ejecuta de forma real en Apache Spark (PySpark). No se utiliza `pandas`, `polars` ni `dask` en ninguna parte del proyecto.

## Estructura del proyecto

```text
prueba_final/
├── .env.example              # Plantilla de variables de entorno (sin secretos)
├── .gitignore                # Reglas de exclusión para Git
├── docker-compose.yml        # Orquestación de contenedores por perfiles (core, ai, metadata)
├── Dockerfile.airflow        # Imagen propia de Airflow con Java 17 y JDBC PostgreSQL
├── requirements.txt          # Dependencias de Python fijadas
├── pytest.ini                # Configuración de pruebas automatizadas
├── README.md                 # Documentación general del proyecto
├── config/                   # Configuraciones globales
├── sql/                      # Scripts DDL de esquemas, tablas y roles
├── dags/                     # DAGs de Apache Airflow
├── src/                      # Código fuente modular
│   ├── common/               # Configuración y utilidades compartidas
│   ├── ingestion/            # Extracción desde la API del USGS
│   ├── processing/           # Procesamiento y transformaciones Spark
│   ├── quality/              # Reglas de validación y cálculo de calidad
│   ├── ai/                   # Integración con Ollama (anomalías y reporte)
│   └── api/                  # Backend FastAPI y canal SSE
├── prompts/                  # Prompts versionados para el modelo local
├── frontend/                 # Interfaz de usuario (React + TS + Tailwind + Leaflet)
├── docs/                     # Documentación de arquitectura y modelo de datos
└── tests/                    # Suite de pruebas unitarias e integración
```

## Ejecución de pruebas

Para ejecutar la suite de pruebas unitarias y de arquitectura:

```bash
pytest
```

## Variables de entorno

Copiar `.env.example` a `.env` antes del despliegue:

```bash
cp .env.example .env
```
