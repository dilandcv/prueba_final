PLAN DE IMPLEMENTACIÓN: PLATAFORMA DE ANÁLISIS SÍSMICO CON ARQUITECTURA MEDALLÓN
1. Rol, objetivo y reglas de trabajo

Actúa como arquitecto de datos y desarrollador full-stack con experiencia en ingeniería de datos, Python, Apache Spark (PySpark), Apache Airflow, PostgreSQL, Docker, FastAPI, React y aplicaciones de IA local.

Necesito diseñar e implementar una plataforma que obtenga información sísmica de la API del USGS, la procese con una arquitectura medallón (Bronze, Silver, Gold) y presente los resultados en un dashboard web.

Mi nivel es principiante. Elige siempre la solución más sencilla que cumpla los requisitos. Evita la sobreingeniería, las abstracciones innecesarias y las tecnologías que no aporten valor. No simplifiques eliminando tecnologías o requisitos obligatorios.

Tecnologías obligatorias (no se eliminan ni se sustituyen)

Apache Airflow, Apache Spark (PySpark), PostgreSQL, FastAPI, React con TypeScript, Tailwind CSS, Leaflet (o equivalente ligero), SSE, Docker Compose, OpenMetadata, Ollama (u otra solución de IA local) y pytest.

Decisión sobre pandas

No se usará pandas en ninguna parte del proyecto. Todo el procesamiento de datos usa PySpark. Las tareas que no son procesamiento de datos (peticiones HTTP, inserciones simples en Bronze, consultas de la API, lectura de Gold por el módulo de IA) usan Python estándar con requests y psycopg. No propongas pandas, Polars ni Dask.

Reglas de trabajo
En esta primera etapa solo analizas y entregas el plan. No escribas código ni modifiques archivos.
Inspecciona primero el repositorio. Si está vacío, indícalo y propón la estructura.
No pidas aclaraciones innecesarias: ante una decisión abierta, elige la opción más simple, justifícala en una línea y declara el supuesto.
Cuando apruebe el plan, la implementación se hará por fases. Al terminar cada fase, detente, resume lo hecho, indica cómo verificarlo y espera mi aprobación antes de continuar.
Entrega primero una versión resumida del plan (unas 3-4 páginas) y amplía solo las secciones que yo pida.
No afirmes que algo funciona si no está implementado y comprobado.
2. Requisitos de hardware y decisiones fijas

Declara los recursos reales necesarios. Toma como referencia 16 GB de RAM y 20 GB de disco libres. Si la configuración completa no cabe en menos, dilo con claridad.

Decisiones ya tomadas (no las reabras):

Spark en modo local[*], sin clúster ni master/worker. Se ejecuta dentro de la imagen de Airflow (imagen propia basada en la oficial, con JRE 17, PySpark y el driver JDBC de PostgreSQL en el classpath). Airflow lanza los trabajos de Spark con spark-submit local (vía BashOperator) o con PySpark dentro de una tarea Python. Elige una de las dos y justifícala.
Configuración mínima de Spark: una SparkSession por ejecución, spark.driver.memory bajo (p. ej. 1g), spark.sql.shuffle.partitions reducido (p. ej. 4) y zona horaria de sesión fijada en UTC.
Perfiles de Docker Compose (profiles): el perfil por defecto levanta el núcleo (PostgreSQL, Airflow, API, frontend). OpenMetadata y Ollama pueden tener perfiles propios durante el desarrollo, pero docker compose up -d debe poder levantar todo con la configuración final (p. ej. con COMPOSE_PROFILES definido en .env).
Bronze es append-only, con el JSON original en una columna JSONB.
Modelo de IA local de 3B parámetros o menos. Elige uno concreto (p. ej. un Qwen 2.5 o Llama 3.2 pequeño) y justifica su consumo de RAM.
Frecuencia de ingesta configurable (INGEST_INTERVAL_MINUTES). Valor inicial recomendado: 15 minutos. Evalúa si 5 minutos es viable (cada ejecución arranca una JVM, y hay límites de la API) y explica por qué no es el valor por defecto.
Prioridad de requisitos: el núcleo (pipeline con Spark, dashboard, IA con fallback, pruebas, seguridad, documentación) es obligatorio. El linaje de OpenMetadata con Airflow es de mejor esfuerzo y no bloqueante. Las consultas en lenguaje natural no se implementan en la primera versión.
3. Fuente de datos e ingesta

Fuente: API pública del USGS.

https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=YYYY-MM-DD&endtime=YYYY-MM-DD&minmagnitude=2.5

La URL es una plantilla: las fechas y los demás parámetros se construyen dinámicamente.

Requisitos
Obtener eventos mediante HTTP en formato GeoJSON, con requests.
Intervalo de fechas y magnitud mínima configurables.
Conservar el feature original completo y extraer lo necesario: identificador, magnitud, fecha y hora, lugar, coordenadas (latitud, longitud), profundidad, indicador de tsunami y fecha de última actualización del evento en origen.
Ingesta incremental con el parámetro updatedafter del USGS, que devuelve eventos nuevos y modificados. Guarda la marca de la última ingesta correcta. Explica la primera carga (p. ej. últimos N días configurables).
Manejar errores HTTP, tiempos de espera, respuestas inválidas, límites de solicitudes (incluido el límite de resultados por consulta de la API) y fallos temporales, con reintentos y espera progresiva.
Registrar fecha de extracción e identificador de lote (batch_id).
Una ejecución fallida debe poder reintentarse sin generar duplicados.

La ingesta es por lotes. No uses Kafka, Redis Streams ni tecnologías de streaming.

4. Arquitectura medallón

Solo existen estas tres capas, cada una en su propio esquema de PostgreSQL: bronze, silver, gold. No diseñes capas ni tablas para registros inválidos.

Bronze
Datos originales de la API, append-only.
Columnas mínimas: event_id, batch_id, ingested_at, source_updated_at, payload (JSONB con el feature original).
Debe permitir reconstruir Silver completamente desde Bronze.
Silver
Eventos normalizados, tipados y validados con Spark.
Una fila por event_id (clave primaria), con la versión más reciente del evento.
Fechas en UTC.
Los registros que fallan una validación se descartan y no continúan. Solo se registran contadores y motivos agregados en la tabla de métricas de calidad y en los logs.
Gold
Datos listos para análisis, calculados con Spark a partir de Silver:
Eventos depurados para consulta y mapa.
Agregados por hora y región.
Distribución por magnitud.
Ranking de regiones.
Base para detección de anomalías (conteos horarios por región).
Los consumidores analíticos (API, dashboard, IA) solo acceden a Gold.
Escritura idempotente desde Spark

Spark JDBC no hace upsert de forma nativa. Patrón obligatorio:

Spark escribe en una tabla de staging (mode("overwrite")).
Una sentencia SQL INSERT ... ON CONFLICT DO UPDATE, ejecutada con psycopg, pasa los datos del staging a la tabla final.

El staging es técnico y temporal, y no constituye una capa adicional; documéntalo en ARQUITECTURA.md.

Requisitos adicionales
Documentar tablas, campos, claves primarias, claves foráneas, relaciones, índices y restricciones.
Operaciones idempotentes con IDs estables del USGS. Procesar dos veces el mismo intervalo no produce duplicados, y un evento actualizado en origen actualiza el existente.
El plan debe explicar el recorrido completo de un evento desde la API hasta Gold y qué ocurre cuando falla una validación.
5. Procesamiento con Apache Spark

Spark debe encargarse realmente de todo el procesamiento Bronze → Silver → Gold. No es una dependencia decorativa.

El plan debe especificar:

Lectura: cómo lee Spark Bronze y Silver desde PostgreSQL por JDBC (incluido cómo manejar la columna JSONB, p. ej. leyéndola como texto con payload::text) y cómo procesa solo los lotes nuevos.
Transformaciones: parseo del JSON con from_json y un esquema explícito, conversión de milisegundos epoch a timestamp UTC, extracción de región desde el campo de lugar, tipado de columnas, deduplicación por event_id conservando la versión más reciente (con Window o equivalente).
Validaciones: cómo se aplican con expresiones de columna (filter, when, condiciones por regla), cómo se cuentan los rechazos por regla y cómo se descartan los inválidos.
Producción de Silver y Gold: groupBy, agg, window para agregados por hora y región, distribución por magnitud, ranking de regiones y conteos para el z-score.
Escritura: staging por JDBC y upsert SQL (sección 4).
Ejecuciones repetidas: cómo se garantiza que reprocesar un intervalo no duplica ni corrompe datos.
Comunicación Airflow ↔ Spark y configuración de Spark en Docker (según la sección 2).
Memoria: cómo se mantiene bajo control (procesar por lotes o por rango de fechas, pocas particiones).

Configuración sencilla, local y sin distribuciones complejas. El código de Spark debe ser corto, claro y comentado en español, de modo que un principiante pueda explicarlo línea por línea. Si una línea no se puede explicar, se simplifica.

Sección obligatoria en docs/ARQUITECTURA.md: “Spark en este proyecto”

Debe responder, con lenguaje sencillo:

Qué es Spark y qué problema resuelve (procesamiento distribuido en memoria).
Qué papel tiene en cada paso del pipeline.
DataFrame de Spark frente a un DataFrame tradicional, y evaluación perezosa (transformaciones frente a acciones).
Qué son las particiones y el shuffle, y dónde ocurren en este pipeline.
Qué significa local[*] y por qué se usa.
Cómo se conecta a PostgreSQL (JDBC) y cómo se logra la idempotencia.
Por qué se usa con un volumen pequeño y cómo escalaría (clúster standalone, YARN o Kubernetes) sin reescribir las transformaciones.
Cómo lo orquesta Airflow y qué ocurre si falla.
6. Orquestación con Airflow

Airflow programa, ejecuta y supervisa. Los DAG no contienen la lógica de negocio: llaman a módulos Python/PySpark independientes y testeables.

DAG principal

Tareas, en orden:

Determinar el intervalo de consulta.
Extraer eventos de la API.
Cargar en Bronze.
Spark: Bronze → Silver (transformar y validar).
Spark: Silver → Gold.
Ejecutar comprobaciones de calidad.
Registrar el resultado de la ejecución.
Marcar los datos como disponibles para la API y el dashboard (origen de la notificación SSE).

Reglas:

Los datos inválidos nunca llegan a Gold.
Definir reintentos, tiempos de espera, límites de ejecución y logs útiles.
Ejecutar el DAG varias veces seguidas no duplica datos ni deja las capas en estado incoherente.
max_active_runs=1 y catchup=False, o justifica lo contrario.
Arranque automático

Tras docker compose up -d, la ingesta debe empezar sola. Explica cómo se logra (p. ej. DAGs activados con AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=False y un servicio de inicialización que espera a que PostgreSQL y Airflow estén sanos) y cómo se evita ejecutar la ingesta antes de que las dependencias, incluidos Java y el driver JDBC, estén listas.

Documentación de DAG

Cada DAG usa doc_md con propósito, frecuencia, tareas y dependencias, entradas y salidas, política de reintentos, errores posibles y forma de verificarlo. Los DAG deben aparecer sin errores de importación.

7. Calidad de datos

Reglas propias implementadas en PySpark y/o SQL, sin frameworks adicionales.

Validaciones mínimas
Existencia del identificador.
Magnitud numérica y dentro de un rango definido en configuración.
Fecha y hora válidas.
Coordenadas dentro de los límites geográficos.
Tipos de datos correctos.
Nulos en campos obligatorios.
Duplicados por identificador.
Validez del indicador de tsunami.
Coherencia de los registros transformados.

Distingue campos obligatorios (p. ej. id, magnitud, fecha, coordenadas) de opcionales (p. ej. lugar o profundidad) para no rechazar eventos por datos que la fuente no siempre trae.

Puntaje de calidad
Fórmula explícita y documentada. Propuesta inicial: puntaje = registros_validos / registros_evaluados × 100, por lote.
Guardar en una tabla de métricas los conteos por regla (p. ej. rechazados_magnitud_invalida), no solo el porcentaje. Así se depura sin almacenar registros inválidos.
El puntaje se calcula con código, nunca con IA, y el dashboard muestra el valor real del pipeline.
8. Seguridad de base de datos y roles

Define al menos tres roles, creados en un script SQL de inicialización:

Rol	Permisos
pipeline	Lectura y escritura en bronze, silver, gold y tablas operativas (usado por Airflow/Spark)
api_reader	Solo lectura sobre Gold
ai_reader	Solo lectura sobre vistas de Gold autorizadas

El modelo de IA nunca tiene acceso a PostgreSQL ni credenciales. El componente que lo invoca consulta Gold con ai_reader y le pasa solo datos ya calculados.

9. Inteligencia artificial local

Ollama (o equivalente) en Docker Compose. El sistema debe:

Descargar y preparar el modelo automáticamente en el primer arranque con un servicio de inicialización (ollama pull).
Distinguir entre “servicio iniciado” y “modelo listo para inferir” (healthcheck que verifica que el modelo existe).
No usar proveedores externos.

La IA solo redacta texto. Los cálculos, las transformaciones y las reglas son responsabilidad del código.

Automatización A: reporte narrativo diario

DAG diario que genera un resumen ejecutivo con datos de Gold: actividad observada, número de eventos, regiones con más actividad, eventos destacados, tendencias e información de contexto. Los cálculos se hacen antes en SQL o PySpark; el modelo solo redacta.

Automatización B: detección de anomalías
Técnica inicial: z-score sobre conteos horarios por región, con umbral configurable, mínimo de observaciones requerido y limitaciones documentadas. Nunca se presenta como predicción de terremotos.
Pasos: consultar Gold → calcular métricas → identificar anomalías → registrar alertas → pedir explicación breve al modelo → validar salida → registrar ejecución.
El cálculo del z-score puede hacerse con Spark (ventanas/agregaciones) o con SQL sobre Gold; elige lo más simple y justifícalo. Sin pandas en ningún caso.
Debe funcionar sin el modelo: si Ollama no está disponible, la explicación se construye con una plantilla determinista.
Controles obligatorios
Salidas estructuradas validadas con Pydantic.
Prompts versionados en el repositorio (prompts/).
Cifras insertadas mediante marcadores que Python sustituye por los valores calculados. Cualquier cifra adicional del modelo se valida o se rechaza.
Reintento acotado ante respuesta inválida y fallback determinista si falla o excede el tiempo.
Los fallos del modelo nunca interrumpen el pipeline principal.
Tabla de seguimiento de ejecuciones de IA

Fecha y hora, tipo de automatización, versión del prompt, modelo, estado, tokens de entrada y salida (si están disponibles), latencia, costo estimado, uso de fallback e identificador de ejecución de Airflow.

Explica cómo se calcula el costo estimado en un modelo local (p. ej. tarifa configurable por token o por segundo de cómputo, con valor por defecto 0) y sus limitaciones. No presentes estimaciones de energía o infraestructura como costos facturados.

10. API y dashboard

Backend FastAPI (consultas con psycopg o SQLAlchemy, sin pandas). Frontend React + TypeScript + Tailwind. Gráficos con una biblioteca compatible con React/TS (p. ej. Recharts). Mapa con Leaflet. Comunicación por HTTP y SSE.

Indicadores
Eventos de las últimas 24 horas.
Magnitud máxima.
Magnitud promedio.
Eventos con alerta de tsunami.
Puntaje de calidad.
Fecha y hora de la última actualización.

Define el periodo, los filtros y las reglas de cada cálculo. Las cifras salen de Gold en PostgreSQL.

Gráficos

Serie temporal de eventos por hora, distribución por magnitud y regiones con mayor actividad. Reaccionan a los filtros y muestran estados vacíos.

Mapa

Eventos por coordenadas con marcadores (magnitud, lugar, fecha, profundidad), sin sobrecargar la interfaz (limita puntos o agrúpalos). Datos desde Gold vía API.

Filtros

Rango de fechas, magnitud mínima y región, aplicados de forma consistente a indicadores, gráficos y mapa.

Actualización sin recargar
SSE notifica al frontend solo después de que el pipeline confirme que los datos están disponibles. El frontend entonces vuelve a consultar los datos afectados.
No se simulan eventos ni datos. Documenta la frecuencia real de ingesta y que depende de la disponibilidad de la API y del tiempo de procesamiento (incluido el arranque de Spark).
Estados de la interfaz

Carga inicial, sin datos, error de conexión, error al consultar indicadores, pérdida de SSE (con reconexión) y recuperación. Se conserva la última información disponible junto con la hora de su última actualización. Nunca pantalla en blanco.

11. OpenMetadata

Debe integrarse de forma funcional, no solo estar instalado:

Despliegue con Docker Compose (verifica la compatibilidad de versiones antes de fijar imágenes).
Conexión con PostgreSQL y descubrimiento de las tablas relevantes.
Descripciones de los activos y etiquetas que identifiquen Bronze, Silver y Gold.
Integración con Airflow para procesos y linaje como mejor esfuerzo: documenta qué se consigue y qué limitaciones tiene.
Automatiza la ingesta de metadatos en lo posible (servicio de inicialización) para respetar el arranque con un solo comando.
12. Docker y ejecución local

docker compose up -d debe levantar: PostgreSQL, Airflow (con inicialización y Spark integrado en su imagen), FastAPI, frontend, Ollama (con preparación automática del modelo), OpenMetadata con sus dependencias y los procesos auxiliares estrictamente necesarios. No hay clúster de Spark ni contenedores master/worker.

Requisitos:

Volúmenes persistentes.
Healthchecks y depends_on con condition: service_healthy.
Variables en .env y un .env.example sin credenciales reales.
Políticas de reinicio razonables que eviten bucles infinitos.
Límites de recursos cuando sea posible.
No exponer puertos internos innecesarios.
Sin servicios redundantes.
Explica que el primer arranque puede tardar varios minutos (construcción de la imagen con Java, descarga del modelo, inicio de OpenMetadata) y cómo comprobar que todo está listo.

Documenta los requisitos previos inevitables (Docker, RAM, disco).

13. Pruebas con pytest

Todo se ejecuta con un único comando: pytest. Pruebas organizadas por componente, sin depender de datos variables de la API pública (usa respuestas GeoJSON de ejemplo y fixtures deterministas).

Cobertura mínima:

Ingesta: interpretación de GeoJSON, errores HTTP, respuestas inválidas o incompletas, intervalos de fechas, prevención de duplicados, uso de updatedafter.
Calidad y procesamiento (Spark): campos obligatorios, magnitudes, coordenadas, normalización de fechas, descarte de inválidos, garantía de que no llegan a Gold, transformaciones Silver → Gold, actualización idempotente, cálculo del puntaje.
Base de datos: escritura y lectura, claves, restricciones, reprocesamiento del mismo intervalo, cálculo de indicadores, permisos de los roles.
IA: validación Pydantic, consistencia de cifras, registro de ejecuciones, respuestas inválidas, fallback, anomalías sin modelo.
API: endpoints, filtros, errores controlados, SSE, ausencia de datos.

Detalles específicos de Spark:

Una única SparkSession compartida mediante un fixture con scope="session" en modo local, con pocas particiones, para que la suite no sea lenta.
Los tests de transformaciones usan DataFrames pequeños y deterministas, y ejecutan Spark de verdad (no se simula).
Documenta que pytest necesita Java y PySpark instalados donde se ejecute (o que se ejecuta dentro del contenedor de Airflow) y explica cuál de las dos opciones se elige.

Los tests unitarios no necesitan el modelo descargado ni servicios externos. Los tests de integración usan una PostgreSQL real de prueba (elige la opción más simple) y no simulan los componentes que se quieren verificar. Documenta las dependencias y garantiza que la suite completa pase antes de dar el proyecto por terminado.

14. Seguridad
Sin credenciales reales en el código ni en archivos versionados.
Permisos de base de datos por componente (sección 8).
Validación de entradas en la API y errores que no revelan información sensible.
Dependencias con versiones fijadas y revisadas (incluida la compatibilidad entre PySpark, Java y el driver JDBC).
Escaneos reproducibles: Gitleaks (secretos), Bandit (código Python) y pip-audit (dependencias). Evalúa si conviene escanear imágenes Docker (p. ej. con Trivy), sobre todo la imagen propia de Airflow con Java.
Explica qué se ejecuta, cómo se interpretan los resultados y dónde se documentan.
Solo se declara un análisis como ejecutado cuando realmente se ejecutó. Si hay hallazgos, se documentan y se corrigen. No se afirma ausencia absoluta de vulnerabilidades: se documenta el alcance.
15. Documentación obligatoria

La documentación debe coincidir con el código real.

README.md: qué hace el proyecto, arquitectura, tecnologías, requisitos previos, docker compose up -d, acceso a servicios, variables de entorno, ejecución por lotes, capas, reglas de calidad, IA, actualización del dashboard, pytest, resultados reales de seguridad, limitaciones, mejoras futuras y cómo detener y reiniciar sin perder datos.
docs/ARQUITECTURA.md: propósito, diagramas Mermaid (componentes y capas), flujo de datos, responsabilidad de cada servicio, justificación de Airflow, Spark, PostgreSQL y OpenMetadata, sección “Spark en este proyecto” (sección 5), IA local, estrategia de actualización, manejo de errores, recursos y seguridad.
docs/MODELO_DATOS.md: tablas por capa, columnas y tipos, claves, restricciones, índices, relaciones, vistas, tablas de alertas y seguimiento, y ejemplos del recorrido de un evento entre capas.
Además: reglas de calidad, variables de entorno, DAG, procedimientos de recuperación y prompts versionados.
16. Estructura de directorios

Propón una estructura simple y modular que separe como mínimo: DAG de Airflow, ingesta, procesamiento con Spark, validaciones, acceso a PostgreSQL, API, frontend, automatizaciones de IA, prompts, pruebas, Docker (incluida la imagen de Airflow con Java y el JAR JDBC), documentación y scripts SQL. Sin módulos con responsabilidades duplicadas. Explica dónde va cada funcionalidad.

17. Criterios de aceptación

El plan debe explicar cómo se verifica cada uno.

Infraestructura

 docker compose up -d inicia los servicios necesarios.
 Airflow muestra los DAG sin errores de importación.
 La primera ingesta comienza automáticamente.
 PostgreSQL conserva los datos tras reiniciar.
 Spark ejecuta realmente las transformaciones Bronze → Silver → Gold dentro del DAG.
 OpenMetadata permite consultar los activos configurados.
 El modelo de IA queda preparado automáticamente.

Pipeline y datos

 Los datos fluyen automáticamente desde el USGS hasta el dashboard.
 Reprocesar un intervalo no duplica eventos.
 Los registros existentes se actualizan correctamente.
 Los datos inválidos no llegan a Gold.
 La calidad se calcula con reglas explícitas.
 Las estadísticas de Gold coinciden con los indicadores de la aplicación.

Inteligencia artificial

 Existe un reporte narrativo diario y una detección de anomalías, ambos en Airflow.
 Los cálculos los hace el código y las salidas del modelo se validan.
 Las cifras publicadas coinciden con los cálculos.
 Los fallos del modelo no interrumpen el procesamiento principal.
 Cada ejecución registra modelo, versión del prompt, tokens, latencia, costo estimado y estado.

Dashboard

 Indicadores, tres gráficos y mapa presentes.
 Filtros consistentes.
 Actualización sin recargar.
 Gestión correcta de ausencia de datos y errores.

Calidad, seguridad y pruebas

 pytest pasa completo.
 Las pruebas verifican idempotencia y reglas de calidad.
 Las análisis de seguridad se ejecutaron y están documentados.
 No hay secretos expuestos, según el alcance revisado.
 La documentación refleja la implementación.
 No existe ninguna dependencia de pandas en el proyecto.
18. Formato de la respuesta (plan)

Entrega, en versión resumida:

A. Diagnóstico inicial del repositorio y riesgos.
B. Arquitectura con diagrama Mermaid y recorrido de un evento.
C. Decisiones técnicas (tabla: componente, responsabilidad, motivo, alternativa descartada, recursos).
D. Modelo de datos (tablas por capa, relaciones, idempotencia, calidad, anomalías y ejecuciones de IA, sin tablas de inválidos).
E. Estructura de directorios.
F. Diseño de los DAG (principal, reporte diario, anomalías) y cómo se integra Spark.
G. API y dashboard (endpoints, filtros, gráficos, mapa, SSE).
H. Pruebas y seguridad.
I. Plan por fases, en este orden de dependencias:
Estructura del repo, .env.example, configuración de pytest.
PostgreSQL: esquemas, tablas, restricciones, roles.
Ingesta en Python (requests + psycopg) con updatedafter y carga a Bronze.
Entorno Spark: imagen con Java, PySpark y JDBC; comprobar que una SparkSession lee y escribe en PostgreSQL desde la terminal.
Spark Bronze → Silver con validaciones y puntaje de calidad.
Spark Silver → Gold con staging + upsert idempotente.
Airflow y DAG principal con arranque automático.
FastAPI.
Frontend.
IA: anomalías determinista primero, luego explicación con modelo y reporte diario.
OpenMetadata.
Seguridad, documentación final (incluida “Spark en este proyecto”) y prueba desde cero (docker compose down -v seguido de up -d).
Para cada fase: objetivo, archivos, cambios, pruebas y criterio de terminado. La documentación y Docker Compose se completan fase a fase, no al final.
J. Riesgos y verificación final, con una solución sencilla por riesgo (Java/JDBC en Docker, RAM, arranque lento de la JVM, compatibilidad de versiones, descarga del modelo, límites de la API, comportamiento de Compose) y una matriz que relacione cada criterio de aceptación con su fase y su forma de comprobación.
Instrucción final

Prioriza una implementación pequeña, funcional, mantenible y comprensible. No añadas tecnologías innecesarias, no uses pandas, no sustituyas Spark por SQL para aparentar su uso, no inventes datos ni resultados, y no afirmes que algo funciona sin haberlo comprobado.

Por ahora entrega solo el plan resumido. No programes ni modifiques el repositorio hasta que lo revise y apruebe.