"""Configuración y fixtures globales de pytest."""
import os
import sys
import types
import pytest
from src.common.config import Settings, get_settings


# Shim ligero de Airflow para entornos donde no está instalado en el host local
try:
    import airflow  # noqa: F401
except ModuleNotFoundError:
    class MockOperator:
        def __init__(self, task_id, python_callable=None, **kwargs):
            self.task_id = task_id
            self.python_callable = python_callable
            self.downstream_list = []
            self.upstream_list = []
            for k, v in kwargs.items():
                setattr(self, k, v)
            if hasattr(MockDAG, "_current_dag") and MockDAG._current_dag:
                MockDAG._current_dag.tasks.append(self)

        def __rshift__(self, other):
            if isinstance(other, (list, tuple)):
                for o in other:
                    self.downstream_list.append(o)
                    o.upstream_list.append(self)
            else:
                self.downstream_list.append(other)
                other.upstream_list.append(self)
            return other

    class MockDAG:
        _current_dag = None

        def __init__(self, dag_id, **kwargs):
            self.dag_id = dag_id
            self.tasks = []
            self.schedule_interval = kwargs.get("schedule")
            for k, v in kwargs.items():
                setattr(self, k, v)

        def __enter__(self):
            MockDAG._current_dag = self
            return self

        def __exit__(self, *args):
            MockDAG._current_dag = None

    airflow_mod = types.ModuleType("airflow")
    airflow_mod.DAG = MockDAG
    airflow_operators = types.ModuleType("airflow.operators")
    airflow_python = types.ModuleType("airflow.operators.python")
    airflow_python.PythonOperator = MockOperator
    airflow_operators.python = airflow_python

    sys.modules["airflow"] = airflow_mod
    sys.modules["airflow.operators"] = airflow_operators
    sys.modules["airflow.operators.python"] = airflow_python


@pytest.fixture
def clean_env(monkeypatch):
    """Fixture para aislar variables de entorno durante las pruebas."""
    monkeypatch.setenv("POSTGRES_HOST", "test-postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("USGS_MIN_MAGNITUDE", "3.0")
    monkeypatch.setenv("INGEST_INTERVAL_MINUTES", "10")
    monkeypatch.setenv("SPARK_MASTER", "local[2]")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    return os.environ


@pytest.fixture
def default_settings() -> Settings:
    """Fixture que devuelve la configuración por defecto."""
    return get_settings()
