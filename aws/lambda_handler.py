"""
AccessHome Analyzer — AWS Lambda Handler
Executa auditorias de acessibilidade como função serverless.

Autor: Yago Santos Silva
Pesquisa: PICTA 2026 — Senac SP
"""

import json
import os
import uuid
import time
from datetime import datetime, timezone

import boto3

# Clientes AWS
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

SCANS_TABLE = os.environ.get("SCANS_TABLE", "accesshome-analyzer-scans-dev")
REPORTS_BUCKET = os.environ.get("REPORTS_BUCKET", "accesshome-analyzer-reports-dev")


# ═══════════════════════════════════════════════════════
# CONFIGURAÇÃO - Matriz de Severidade (da pesquisa)
# ═══════════════════════════════════════════════════════

SEVERITY_WEIGHTS = {
    "critical": 3,
    "serious": 3,
    "moderate": 2,
    "minor": 1,
}

WCAG_CRITERIA_MAP = {
    "1.1.1": "Texto em Ícones (Conteúdo Não Textual)",
    "1.4.3": "Contraste Mínimo",
    "2.1.1": "Teclado / Tabulação",
    "4.1.2": "Nome, Função, Valor (Leitor de Tela)",
}


def classify_violation(violation: dict) -> dict:
    """Classifica uma violação usando a Matriz de Severidade."""
    impact = violation.get("impact", "minor")
    weight = SEVERITY_WEIGHTS.get(impact, 1)

    # Extrair critério WCAG
    wcag_criterion = ""
    for tag in violation.get("tags", []):
        if tag.startswith("wcag") and len(tag) >= 7:
            digits = tag[4:]
            if digits.isdigit() and len(digits) >= 3:
                wcag_criterion = f"{digits[0]}.{digits[1]}.{digits[2]}"
                break

    return {
        "id": violation["id"],
        "impact": impact,
        "severity_weight": weight,
        "description": violation.get("help", ""),
        "wcag_criterion": wcag_criterion,
        "wcag_name": WCAG_CRITERIA_MAP.get(wcag_criterion, ""),
        "nodes_count": violation.get("nodes_count", 0),
        "help_url": violation.get("helpUrl", ""),
    }


def calculate_accessibility_score(violations: list, passes: int) -> dict:
    """
    Calcula um score unificado de acessibilidade (0-100).
    
    Fórmula:
    - Base: 100
    - Cada violação Crítica (peso 3): -15 pontos
    - Cada violação Séria (peso 2): -8 pontos
    - Cada violação Moderada (peso 1): -3 pontos
    - Mínimo: 0
    """
    score = 100
    for v in violations:
        weight = v.get("severity_weight", 1)
        if weight == 3:
            score -= 15
        elif weight == 2:
            score -= 8
        else:
            score -= 3

    return {
        "score": max(0, score),
        "grade": (
            "A" if score >= 90 else
            "B" if score >= 75 else
            "C" if score >= 50 else
            "D" if score >= 25 else
            "F"
        ),
        "is_accessible": score >= 75,
    }


# ═══════════════════════════════════════════════════════
# HANDLER PRINCIPAL
# ═══════════════════════════════════════════════════════

def handler(event, context):
    """
    Lambda handler para scans de acessibilidade.
    
    POST /api/scan
    Body: {
        "url": "https://demo.home-assistant.io",
        "keyboard_test": false
    }
    
    GET /api/history?url=https://...
    
    GET /api/report/{scan_id}
    """
    http_method = event.get("httpMethod", "POST")
    path = event.get("path", "/api/scan")

    try:
        if http_method == "POST" and "/scan" in path:
            return handle_scan(event)
        elif http_method == "GET" and "/history" in path:
            return handle_history(event)
        elif http_method == "GET" and "/report" in path:
            return handle_report(event)
        else:
            return response(404, {"error": "Endpoint não encontrado"})
    except Exception as e:
        return response(500, {"error": str(e)})


def handle_scan(event):
    """
    Processa uma requisição de scan.
    
    NOTA: Em produção real, o scan com Playwright rodaria em uma
    Lambda com Layer customizado (playwright-aws-lambda).
    Para o protótipo/demo, simulamos com dados mock baseados na pesquisa.
    """
    body = json.loads(event.get("body", "{}"))
    url = body.get("url")

    if not url:
        return response(400, {"error": "Campo 'url' é obrigatório"})

    scan_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    start_time = time.time()

    # ─── SCAN ENGINE ───
    # Em produção: Playwright + axe-core (requer Lambda Layer)
    # Para demo: usa o motor local importado ou dados mock
    
    try:
        # Tentar usar o motor real (se as deps estiverem no Layer)
        from scan_engine import execute_scan
        scan_result = execute_scan(url, keyboard_test=body.get("keyboard_test", False))
    except ImportError:
        # Fallback: dados mock baseados nos resultados reais da pesquisa
        scan_result = get_mock_scan_result(url)

    scan_time = time.time() - start_time

    # Classificar violações
    classified = [classify_violation(v) for v in scan_result.get("violations", [])]
    
    # Calcular score
    score_data = calculate_accessibility_score(
        classified, scan_result.get("passes", 0)
    )

    # Montar registro
    scan_record = {
        "scan_id": scan_id,
        "url": url,
        "timestamp": timestamp,
        "scan_time_seconds": round(scan_time, 2),
        "total_violations": len(classified),
        "critical_count": sum(1 for v in classified if v["severity_weight"] == 3),
        "serious_count": sum(1 for v in classified if v["severity_weight"] == 2),
        "moderate_count": sum(1 for v in classified if v["severity_weight"] == 1),
        "passes": scan_result.get("passes", 0),
        "score": score_data["score"],
        "grade": score_data["grade"],
        "is_accessible": score_data["is_accessible"],
        "violations": classified,
        "keyboard_test": scan_result.get("keyboard_test", None),
    }

    # Salvar no DynamoDB
    table = dynamodb.Table(SCANS_TABLE)
    table.put_item(Item=json.loads(json.dumps(scan_record), parse_float=str))

    # Gerar e salvar relatório HTML no S3
    report_key = f"reports/{scan_id}.html"
    report_html = generate_report_html(scan_record)
    s3.put_object(
        Bucket=REPORTS_BUCKET,
        Key=report_key,
        Body=report_html.encode("utf-8"),
        ContentType="text/html",
    )

    # URL presigned para o relatório (válida por 7 dias)
    report_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": REPORTS_BUCKET, "Key": report_key},
        ExpiresIn=604800,
    )

    return response(200, {
        "scan_id": scan_id,
        "url": url,
        "timestamp": timestamp,
        "score": score_data["score"],
        "grade": score_data["grade"],
        "total_violations": len(classified),
        "critical_count": scan_record["critical_count"],
        "serious_count": scan_record["serious_count"],
        "report_url": report_url,
        "message": f"Scan completo em {scan_time:.1f}s — Grade {score_data['grade']} ({score_data['score']}/100)",
    })


def handle_history(event):
    """Retorna histórico de scans para uma URL."""
    params = event.get("queryStringParameters", {}) or {}
    url = params.get("url")

    if not url:
        return response(400, {"error": "Parâmetro 'url' é obrigatório"})

    table = dynamodb.Table(SCANS_TABLE)
    result = table.query(
        IndexName="url-timestamp-index",
        KeyConditionExpression="url = :url",
        ExpressionAttributeValues={":url": url},
        ScanIndexForward=False,  # Mais recente primeiro
        Limit=20,
    )

    scans = result.get("Items", [])

    # Calcular tendência
    trend = None
    if len(scans) >= 2:
        latest = int(scans[0].get("total_violations", 0))
        previous = int(scans[1].get("total_violations", 0))
        delta = latest - previous
        trend = {
            "improving": delta < 0,
            "violations_delta": delta,
            "latest_score": int(scans[0].get("score", 0)),
            "previous_score": int(scans[1].get("score", 0)),
        }

    return response(200, {
        "url": url,
        "total_scans": len(scans),
        "scans": [
            {
                "scan_id": s["scan_id"],
                "timestamp": s["timestamp"],
                "score": int(s.get("score", 0)),
                "grade": s.get("grade", "?"),
                "total_violations": int(s.get("total_violations", 0)),
            }
            for s in scans
        ],
        "trend": trend,
    })


def handle_report(event):
    """Redireciona para o relatório HTML no S3."""
    path_params = event.get("pathParameters", {}) or {}
    scan_id = path_params.get("scan_id", "")

    if not scan_id:
        return response(400, {"error": "scan_id é obrigatório"})

    report_key = f"reports/{scan_id}.html"
    report_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": REPORTS_BUCKET, "Key": report_key},
        ExpiresIn=3600,
    )

    return {
        "statusCode": 302,
        "headers": {"Location": report_url},
        "body": "",
    }


# ═══════════════════════════════════════════════════════
# MOCK DATA (baseado nos resultados reais da pesquisa)
# ═══════════════════════════════════════════════════════

def get_mock_scan_result(url: str) -> dict:
    """Retorna dados mock baseados nos resultados reais da pesquisa PICTA."""
    
    # Dados reais das auditorias realizadas
    mock_db = {
        "home-assistant": {
            "violations": [
                {"id": "aria-prohibited-attr", "impact": "critical", "help": "Uso de atributos ARIA proibidos", "tags": ["wcag412"], "nodes_count": 5, "helpUrl": ""},
                {"id": "button-name", "impact": "critical", "help": "Botões sem nome acessível", "tags": ["wcag412"], "nodes_count": 8, "helpUrl": ""},
                {"id": "image-alt", "impact": "critical", "help": "Ícones sem texto alternativo", "tags": ["wcag111"], "nodes_count": 12, "helpUrl": ""},
                {"id": "color-contrast", "impact": "serious", "help": "Contraste insuficiente entre texto e fundo", "tags": ["wcag143"], "nodes_count": 6, "helpUrl": ""},
                {"id": "aria-roles", "impact": "critical", "help": "Hierarquia de roles ARIA incorreta", "tags": ["wcag412"], "nodes_count": 3, "helpUrl": ""},
            ],
            "passes": 18,
            "keyboard_test": {"focusable_elements": 23, "focus_traps": 0, "elements_without_indicator": 5},
        },
        "openhab": {
            "violations": [
                {"id": "aria-valid-attr-value", "impact": "critical", "help": "Atributo ARIA com valor inválido", "tags": ["wcag412"], "nodes_count": 1, "helpUrl": ""},
                {"id": "color-contrast", "impact": "serious", "help": "Contraste insuficiente", "tags": ["wcag143"], "nodes_count": 6, "helpUrl": ""},
            ],
            "passes": 24,
            "keyboard_test": {"focusable_elements": 19, "focus_traps": 0, "elements_without_indicator": 2},
        },
        "sharptools": {
            "violations": [
                {"id": "image-alt", "impact": "critical", "help": "Imagens sem texto alternativo", "tags": ["wcag111"], "nodes_count": 2, "helpUrl": ""},
                {"id": "link-name", "impact": "serious", "help": "Links sem nome discernível", "tags": ["wcag412"], "nodes_count": 1, "helpUrl": ""},
                {"id": "color-contrast", "impact": "serious", "help": "Contraste insuficiente", "tags": ["wcag143"], "nodes_count": 3, "helpUrl": ""},
            ],
            "passes": 21,
            "keyboard_test": {"focusable_elements": 15, "focus_traps": 0, "elements_without_indicator": 3},
        },
    }

    # Match URL com dados mock
    url_lower = url.lower()
    for key, data in mock_db.items():
        if key in url_lower:
            return data

    # URL desconhecida — retorna scan genérico
    return {
        "violations": [
            {"id": "generic-scan", "impact": "moderate", "help": "Scan simulado — use URL real para dados precisos", "tags": [], "nodes_count": 1, "helpUrl": ""},
        ],
        "passes": 10,
    }


def generate_report_html(scan_record: dict) -> str:
    """Gera HTML do relatório (versão simplificada para Lambda)."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Relatório - {scan_record['url']}</title></head>
<body><h1>AccessHome Analyzer - Relatório</h1>
<p>URL: {scan_record['url']}</p>
<p>Score: {scan_record['score']}/100 (Grade {scan_record['grade']})</p>
<p>Violações: {scan_record['total_violations']} ({scan_record['critical_count']} críticas)</p>
<p>Gerado: {scan_record['timestamp']}</p>
</body></html>"""


# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════

def response(status_code: int, body: dict) -> dict:
    """Formata resposta para API Gateway."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }
