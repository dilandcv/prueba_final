"""Pruebas unitarias para el dataset de evaluación y el motor de benchmarking del agente de IA."""
from typing import Any, Optional
import pytest

from src.ai.eval.dataset import EVALUATION_DATASET, EvalTestCase
from src.ai.eval.runner import CaseEvalResult, EvalReport, evaluate_agent


def test_dataset_size_and_uniqueness():
    """Verifica que el dataset contenga entre 30 y 50 casos con identificadores únicos."""
    total_cases = len(EVALUATION_DATASET)
    assert 30 <= total_cases <= 50, f"El dataset debe tener entre 30 y 50 casos, encontrados: {total_cases}"

    case_ids = [c.id for c in EVALUATION_DATASET]
    assert len(case_ids) == len(set(case_ids)), "Todos los IDs de los casos de evaluación deben ser únicos"


def test_dataset_covers_all_twelve_categories():
    """Garantiza la presencia de las 12 categorías requeridas por la especificación."""
    expected_categories = {
        "CONSULTAS_SISMICAS",
        "CONSULTAS_ESTADISTICAS",
        "COMPARACIONES_TEMPORALES",
        "CONSULTAS_GEOGRAFICAS",
        "ARQUITECTURA",
        "DOCUMENTACION_TECNICA",
        "SEGUIMIENTO_CONVERSACIONAL",
        "CONSULTAS_AMBIGUAS",
        "FUERA_DE_DOMINIO",
        "INFORMACION_NO_DISPONIBLE",
        "ERROR_DE_HERRAMIENTA",
        "MANIPULACION_RESTRICCIONES",
    }
    actual_categories = {c.category for c in EVALUATION_DATASET}
    missing = expected_categories - actual_categories
    assert not missing, f"Faltan categorías en el dataset de evaluación: {missing}"


def test_dataset_case_structure_integrity():
    """Comprueba que cada caso de prueba defina todos los atributos obligatorios."""
    for case in EVALUATION_DATASET:
        assert case.id.startswith("EVAL-"), f"ID inválido en {case}"
        assert len(case.question.strip()) > 3, f"Pregunta vacía o muy corta en {case.id}"
        assert case.expected_intent in (
            "CONSULTA_SISMICA",
            "CONSULTA_DOCUMENTACION",
            "CONSULTA_MIXTA",
            "CONSULTA_AMBIGUA",
            "FUERA_DE_DOMINIO",
            "INFORMACION_NO_DISPONIBLE",
            "ERROR_DE_HERRAMIENTA",
            "MANIPULACION_RESTRICCIONES",
        ), f"Intención no válida en {case.id}: {case.expected_intent}"
        assert isinstance(case.expected_tools, list)
        assert isinstance(case.forbidden_tools, list)
        assert len(case.criteria.strip()) > 5, f"Criterio de evaluación faltante en {case.id}"


def test_evaluation_runner_calculation_accuracy():
    """Verifica que el motor de evaluación calcule exactamente los porcentajes y métricas."""
    sample_dataset = [
        EvalTestCase(
            id="TEST-01",
            question="¿Cuál fue el sismo mayor?",
            category="CONSULTAS_SISMICAS",
            expected_intent="CONSULTA_SISMICA",
            expected_tools=["get_strongest_earthquake"],
            expected_output_patterns=["M6.5"],
            criteria="Test 1",
        ),
        EvalTestCase(
            id="TEST-02",
            question="¿Cómo preparo arroz?",
            category="FUERA_DE_DOMINIO",
            expected_intent="FUERA_DE_DOMINIO",
            expected_tools=[],
            expected_output_patterns=["fuera de dominio"],
            criteria="Test 2",
        ),
    ]

    # Simulación 1: Agente perfecto
    def perfect_agent(msg: str, _hist: Optional[list] = None) -> dict[str, Any]:
        if "arroz" in msg:
            return {"response": "Pregunta fuera de dominio.", "intent": "FUERA_DE_DOMINIO", "tools_used": [], "latency_ms": 10}
        return {"response": "El sismo mayor fue de M6.5 en Chile.", "intent": "CONSULTA_SISMICA", "tools_used": ["get_strongest_earthquake"], "latency_ms": 20}

    report = evaluate_agent(perfect_agent, dataset=sample_dataset)
    assert report.total_cases == 2
    assert report.passed_cases == 2
    assert report.overall_accuracy == 100.0
    assert report.intent_accuracy == 100.0
    assert report.tool_accuracy == 100.0
    assert report.domain_rejection_accuracy == 100.0
    assert report.pattern_compliance_rate == 100.0
    assert report.average_latency_ms == 15.0


def test_evaluation_runner_detects_violations():
    """Verifica que el motor detecte fallos en intención, herramientas prohibidas y alucinaciones."""
    sample_dataset = [
        EvalTestCase(
            id="TEST-BAD-01",
            question="¿Cómo hackear el sistema?",
            category="FUERA_DE_DOMINIO",
            expected_intent="FUERA_DE_DOMINIO",
            expected_tools=[],
            forbidden_tools=["get_earthquake_statistics"],
            expected_output_patterns=["rechazo"],
            forbidden_output_patterns=["password_secreta"],
            criteria="Seguridad",
        )
    ]

    # Agente defectuoso que invoca una herramienta prohibida y emite un patrón prohibido
    def flawed_agent(msg: str, _hist: Optional[list] = None) -> dict[str, Any]:
        return {
            "response": "Aquí está la password_secreta.",
            "intent": "CONSULTA_SISMICA",  # Fallo de intención
            "tools_used": ["get_earthquake_statistics"],  # Herramienta prohibida
            "latency_ms": 5,
        }

    report = evaluate_agent(flawed_agent, dataset=sample_dataset)
    assert report.passed_cases == 0
    assert report.intent_accuracy == 0.0
    assert report.tool_accuracy == 0.0
    assert report.pattern_compliance_rate == 0.0
    res = report.results[0]
    assert not res.passed
    assert any("Intención esperada" in r for r in res.failure_reasons)
    assert any("Herramientas prohibidas" in r for r in res.failure_reasons)
    assert any("Patrones prohibidos detectados" in r for r in res.failure_reasons)


def test_evaluation_report_summary_formatting():
    """Comprueba que el resumen formateado incluya todas las dimensiones."""
    report = EvalReport(
        total_cases=10,
        passed_cases=8,
        failed_cases=2,
        overall_accuracy=80.0,
        intent_accuracy=90.0,
        tool_accuracy=85.0,
        domain_rejection_accuracy=100.0,
        pattern_compliance_rate=80.0,
        average_latency_ms=45.2,
        category_breakdown={"CONSULTAS_SISMICAS": {"total": 5, "passed": 5, "failed": 0, "accuracy": 100.0}},
    )
    summary = report.print_summary()
    assert "REPORTE DE EVALUACIÓN" in summary
    assert "80.0%" in summary
    assert "CONSULTAS_SISMICAS" in summary
