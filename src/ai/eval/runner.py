"""Motor de ejecución y evaluación cuantitativa reproducible para el agente de IA."""
from dataclasses import asdict, dataclass, field
import json
import logging
import time
from typing import Any, Callable, Optional

from src.ai.eval.dataset import EVALUATION_DATASET, EvalTestCase


logger = logging.getLogger(__name__)


@dataclass
class CaseEvalResult:
    """Resultado de la evaluación de un caso individual."""
    case_id: str
    question: str
    category: str
    passed: bool
    intent_match: bool
    tools_match: bool
    patterns_match: bool
    forbidden_clean: bool
    actual_intent: str
    actual_tools: list[str]
    response_preview: str
    latency_ms: int
    failure_reasons: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    """Reporte consolidado de métricas tras ejecutar la suite de evaluación."""
    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_accuracy: float
    intent_accuracy: float
    tool_accuracy: float
    domain_rejection_accuracy: float
    pattern_compliance_rate: float
    average_latency_ms: float
    category_breakdown: dict[str, dict[str, Any]]
    results: list[CaseEvalResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convierte el reporte a un diccionario serializable."""
        return asdict(self)

    def print_summary(self) -> str:
        """Genera un resumen formateado para consola o logs."""
        lines = [
            "================================================================================",
            "                   REPORTE DE EVALUACIÓN DEL AGENTE DE IA                       ",
            "================================================================================",
            f"Total Casos Evaluados:        {self.total_cases}",
            f"Casos Exitosos:               {self.passed_cases} ({self.overall_accuracy:.1f}%)",
            f"Casos Fallidos:               {self.failed_cases}",
            "--------------------------------------------------------------------------------",
            "MÉTRICAS POR DIMENSIÓN:",
            f"- Exactitud de Intención:     {self.intent_accuracy:.1f}%",
            f"- Selección de Herramientas:  {self.tool_accuracy:.1f}%",
            f"- Rechazo de Fuera de Dominio:{self.domain_rejection_accuracy:.1f}%",
            f"- Cumplimiento de Patrones:   {self.pattern_compliance_rate:.1f}%",
            f"- Latencia Promedio:          {self.average_latency_ms:.1f} ms",
            "--------------------------------------------------------------------------------",
            "DESGLOSE POR CATEGORÍA:",
        ]
        for cat, stats in self.category_breakdown.items():
            acc = stats.get("accuracy", 0.0)
            passed = stats.get("passed", 0)
            total = stats.get("total", 0)
            lines.append(f"  • {cat:<28} {passed}/{total} ({acc:.1f}%)")
        lines.append("================================================================================")
        return "\n".join(lines)


def evaluate_agent(
    agent_callable: Callable[[str, Optional[list[dict[str, str]]]], dict[str, Any]],
    dataset: Optional[list[EvalTestCase]] = None,
) -> EvalReport:
    """Ejecuta la suite de evaluación contra una función de agente.

    agent_callable debe recibir (message: str, history: Optional[list]) y retornar un dict con:
    - 'response': str
    - 'intent': str
    - 'tools_used': list[str]
    - 'latency_ms': Optional[int]
    """
    cases = dataset or EVALUATION_DATASET
    results: list[CaseEvalResult] = []

    intent_hits = 0
    tool_hits = 0
    domain_rejection_cases = 0
    domain_rejection_hits = 0
    pattern_hits = 0
    total_latency = 0

    category_stats: dict[str, dict[str, int]] = {}

    for case in cases:
        if case.category not in category_stats:
            category_stats[case.category] = {"total": 0, "passed": 0}
        category_stats[case.category]["total"] += 1

        t_start = time.time()
        try:
            agent_output = agent_callable(case.question, case.context_history)
        except Exception as exc:
            agent_output = {
                "response": f"ERROR INESPERADO: {exc}",
                "intent": "ERROR_DE_HERRAMIENTA",
                "tools_used": [],
                "latency_ms": int((time.time() - t_start) * 1000),
            }

        elapsed_ms = agent_output.get("latency_ms", int((time.time() - t_start) * 1000))
        total_latency += elapsed_ms

        response_text = agent_output.get("response", "")
        actual_intent = agent_output.get("intent", "DESCONOCIDO")
        actual_tools = agent_output.get("tools_used", [])

        # 1. Comprobación de Intención
        # Aceptamos coincidencia exacta o equivalencia entre FUERA_DE_DOMINIO y MANIPULACION_RESTRICCIONES
        intent_match = (
            actual_intent == case.expected_intent
            or (case.expected_intent in ("FUERA_DE_DOMINIO", "MANIPULACION_RESTRICCIONES") and actual_intent in ("FUERA_DE_DOMINIO", "MANIPULACION_RESTRICCIONES"))
        )
        if intent_match:
            intent_hits += 1

        # 2. Comprobación de Herramientas
        # - Ninguna herramienta prohibida debe haber sido llamada
        forbidden_clean = not any(tool in actual_tools for tool in case.forbidden_tools)
        # - Si se esperaban herramientas, deben haber sido llamadas
        tools_match = forbidden_clean and (
            all(t in actual_tools for t in case.expected_tools)
            if case.expected_tools
            else len(actual_tools) == 0
        )
        if tools_match:
            tool_hits += 1

        # 3. Comprobación de Rechazo de Dominio
        is_rejection_case = len(case.expected_tools) == 0 and case.category in ("FUERA_DE_DOMINIO", "MANIPULACION_RESTRICCIONES", "CONSULTAS_AMBIGUAS")
        if is_rejection_case:
            domain_rejection_cases += 1
            if len(actual_tools) == 0 and intent_match:
                domain_rejection_hits += 1

        # 4. Comprobación de Patrones de Texto
        resp_lower = response_text.lower()
        patterns_match = (
            all(pat.lower() in resp_lower for pat in case.expected_output_patterns)
            if case.expected_output_patterns
            else True
        )
        forbidden_patterns_clean = not any(pat.lower() in resp_lower for pat in case.forbidden_output_patterns)

        if patterns_match and forbidden_patterns_clean:
            pattern_hits += 1

        # Determinación de éxito global del caso
        failure_reasons = []
        if not intent_match:
            failure_reasons.append(f"Intención esperada '{case.expected_intent}', obtenida '{actual_intent}'")
        if not tools_match:
            failure_reasons.append(f"Herramientas esperadas {case.expected_tools}, obtenidas {actual_tools}")
        if not forbidden_clean:
            failure_reasons.append(f"Herramientas prohibidas invocadas: {[t for t in actual_tools if t in case.forbidden_tools]}")
        if not patterns_match:
            missing = [p for p in case.expected_output_patterns if p.lower() not in resp_lower]
            failure_reasons.append(f"Patrones esperados faltantes: {missing}")
        if not forbidden_patterns_clean:
            found = [p for p in case.forbidden_output_patterns if p.lower() in resp_lower]
            failure_reasons.append(f"Patrones prohibidos detectados: {found}")

        case_passed = len(failure_reasons) == 0
        if case_passed:
            category_stats[case.category]["passed"] += 1

        results.append(
            CaseEvalResult(
                case_id=case.id,
                question=case.question,
                category=case.category,
                passed=case_passed,
                intent_match=intent_match,
                tools_match=tools_match,
                patterns_match=patterns_match,
                forbidden_clean=forbidden_clean and forbidden_patterns_clean,
                actual_intent=actual_intent,
                actual_tools=actual_tools,
                response_preview=response_text[:120] + "..." if len(response_text) > 120 else response_text,
                latency_ms=elapsed_ms,
                failure_reasons=failure_reasons,
            )
        )

    total_cases = len(cases)
    passed_cases = sum(1 for r in results if r.passed)
    failed_cases = total_cases - passed_cases

    category_breakdown = {}
    for cat, data in category_stats.items():
        total_cat = data["total"]
        passed_cat = data["passed"]
        category_breakdown[cat] = {
            "total": total_cat,
            "passed": passed_cat,
            "failed": total_cat - passed_cat,
            "accuracy": round((passed_cat / total_cat) * 100.0, 2) if total_cat > 0 else 0.0,
        }

    return EvalReport(
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        overall_accuracy=round((passed_cases / total_cases) * 100.0, 2) if total_cases > 0 else 0.0,
        intent_accuracy=round((intent_hits / total_cases) * 100.0, 2) if total_cases > 0 else 0.0,
        tool_accuracy=round((tool_hits / total_cases) * 100.0, 2) if total_cases > 0 else 0.0,
        domain_rejection_accuracy=round((domain_rejection_hits / domain_rejection_cases) * 100.0, 2) if domain_rejection_cases > 0 else 100.0,
        pattern_compliance_rate=round((pattern_hits / total_cases) * 100.0, 2) if total_cases > 0 else 0.0,
        average_latency_ms=round(total_latency / total_cases, 2) if total_cases > 0 else 0.0,
        category_breakdown=category_breakdown,
        results=results,
    )


if __name__ == "__main__":
    # Ejecución de prueba rápida sobre el agente actual como línea base
    from src.ai.chat_service import process_chat_message

    def legacy_adapter(msg: str, hist: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
        resp = process_chat_message(msg)
        return {
            "response": resp.response,
            "intent": "CONSULTA_SISMICA",  # El agente antiguo asume todo como sismos
            "tools_used": ["calculate_daily_summary_metrics"],  # Siempre ejecuta 24h
            "latency_ms": 50,
        }

    report = evaluate_agent(legacy_adapter)
    print(report.print_summary())
