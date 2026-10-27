"""Pruebas técnicas para el entorno de Apache Spark, Java 17 y JDBC PostgreSQL."""
from pathlib import Path
import subprocess
import pytest
from src.processing.spark_session import (
    build_spark_session,
    get_jdbc_properties,
    get_jdbc_url,
    get_spark_session,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_java_availability():
    """Verifica que Java 17 (OpenJDK) esté disponible en el sistema."""
    result = subprocess.run(
        ["java", "-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stderr + result.stdout
    assert result.returncode == 0, f"Java no está disponible: {output}"
    assert "17." in output or "openjdk" in output.lower(), f"Se requiere Java 17 OpenJDK: {output}"


def test_pyspark_installed_version():
    """Verifica que PySpark esté instalado con la versión compatible 3.5.1."""
    import pyspark
    assert pyspark.__version__ == "3.5.1", f"Versión inesperada de PySpark: {pyspark.__version__}"


def test_spark_session_conservative_configuration():
    """Verifica que la SparkSession aplique los parámetros de memoria, particiones y UTC."""
    with get_spark_session("ConfigTest", master="local[1]") as spark:
        conf = spark.sparkContext.getConf()
        assert conf.get("spark.master") == "local[1]"
        assert conf.get("spark.driver.memory") == "1g"
        assert spark.conf.get("spark.sql.shuffle.partitions") == "4"
        assert spark.conf.get("spark.sql.session.timeZone") == "UTC"
        assert spark.conf.get("spark.ui.enabled") == "false"


def test_jdbc_driver_loaded_in_jvm():
    """Verifica que el driver JDBC de PostgreSQL esté presente en el classpath de la JVM."""
    with get_spark_session("JDBCTest", master="local[1]") as spark:
        driver_cls = spark._jvm.java.lang.Class.forName("org.postgresql.Driver")
        assert driver_cls is not None
        assert driver_cls.getName() == "org.postgresql.Driver"


def test_spark_dataframe_native_transformations():
    """Verifica que Spark ejecute transformaciones analíticas en memoria sin errores."""
    with get_spark_session("DataTransformTest", master="local[1]") as spark:
        df = spark.sql("""
            SELECT 'evt_1' as id, 4.5 as mag, 'Region A' as region
            UNION ALL
            SELECT 'evt_2' as id, 2.1 as mag, 'Region A' as region
            UNION ALL
            SELECT 'evt_3' as id, 5.2 as mag, 'Region B' as region
        """)

        # Filtro de magnitud mínima (regla de calidad)
        filtered = df.filter("mag >= 2.5")
        assert filtered.count() == 2

        # Agregación por región
        agg_df = filtered.groupBy("region").count()
        results = {row["region"]: row["count"] for row in agg_df.collect()}
        assert results["Region A"] == 1
        assert results["Region B"] == 1


def test_jdbc_helper_configuration():
    """Verifica la generación de la URL JDBC y propiedades de conexión para los roles."""
    url = get_jdbc_url(host="localhost", port=5432, db="seismic_test")
    assert url == "jdbc:postgresql://localhost:5432/seismic_test"

    pipeline_props = get_jdbc_properties("pipeline")
    assert pipeline_props["user"] == "pipeline"
    assert pipeline_props["driver"] == "org.postgresql.Driver"

    api_props = get_jdbc_properties("api_reader")
    assert api_props["user"] == "api_reader"
    assert api_props["driver"] == "org.postgresql.Driver"


def test_dockerfile_airflow_specifications():
    """Garantiza que Dockerfile.airflow declare Java 17, PySpark y el driver JDBC compatible."""
    dockerfile_path = PROJECT_ROOT / "Dockerfile.airflow"
    assert dockerfile_path.exists(), "Dockerfile.airflow debe existir"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "apache/airflow:2.10.0-python3.11" in content
    assert "openjdk-17-jre-headless" in content
    assert "postgresql-42.7.3.jar" in content
    assert "ENV JAVA_HOME" in content
    assert "ENV SPARK_CLASSPATH" in content
