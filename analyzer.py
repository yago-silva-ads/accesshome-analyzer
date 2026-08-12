"""
AccessHome Analyzer v1.0
Ferramenta de auditoria de acessibilidade para interfaces de Smart Home.

Autor: Yago Santos Silva
Pesquisa: PICTA 2026 — Senac SP
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌ Playwright não instalado. Execute: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    console = Console()
except ImportError:
    print("❌ Rich não instalado. Execute: pip install rich")
    sys.exit(1)


# ═══════════════════════════════════════════════════════
# CONFIGURAÇÃO - Axe-core CDN
# ═══════════════════════════════════════════════════════
AXE_CDN = "https://cdn.jsdelivr.net/npm/axe-core@4.9.1/axe.min.js"

# Mapeamento WCAG → Critérios da pesquisa
WCAG_CRITERIA_MAP = {
    "1.1.1": "Texto em Ícones",
    "1.4.3": "Contraste Mínimo",
    "2.1.1": "Teclado / Tabulação",
    "4.1.2": "Nome, Função, Valor",
}

# Matriz de Severidade (baseada na pesquisa)
SEVERITY_WEIGHTS = {
    "critical": 3,
    "serious": 3,
    "moderate": 2,
    "minor": 1,
}


@dataclass
class Violation:
    """Representa uma violação de acessibilidade detectada."""
    id: str
    impact: str
    description: str
    help: str
    help_url: str
    wcag_tags: list = field(default_factory=list)
    nodes_count: int = 0
    severity_weight: int = 0
    wcag_criterion: str = ""


@dataclass
class KeyboardResult:
    """Resultado do teste de navegação por teclado."""
    focusable_elements: int = 0
    focus_traps: list = field(default_factory=list)
    elements_without_indicator: int = 0
    tab_sequence: list = field(default_factory=list)
    success: bool = True


@dataclass
class AuditReport:
    """Relatório completo da auditoria."""
    url: str
    timestamp: str
    scan_time: float = 0.0
    violations: list = field(default_factory=list)
    passes: int = 0
    incomplete: int = 0
    keyboard_result: Optional[KeyboardResult] = None
    screenshot_path: Optional[str] = None

    @property
    def total_violations(self):
        return len(self.violations)

    @property
    def critical_count(self):
        return sum(1 for v in self.violations if v.severity_weight == 3)

    @property
    def serious_count(self):
        return sum(1 for v in self.violations if v.severity_weight == 2)

    @property
    def moderate_count(self):
        return sum(1 for v in self.violations if v.severity_weight == 1)


# ═══════════════════════════════════════════════════════
# ENGINE - Auditoria com axe-core via Playwright
# ═══════════════════════════════════════════════════════

async def run_axe_audit(page) -> dict:
    """Injeta axe-core na página e executa auditoria WCAG 2.1 AA."""
    # Injetar axe-core
    await page.add_script_tag(url=AXE_CDN)
    await page.wait_for_timeout(1000)

    # Executar auditoria
    results = await page.evaluate("""
        async () => {
            const results = await axe.run(document, {
                runOnly: {
                    type: 'tag',
                    values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']
                }
            });
            return {
                violations: results.violations.map(v => ({
                    id: v.id,
                    impact: v.impact,
                    description: v.description,
                    help: v.help,
                    helpUrl: v.helpUrl,
                    tags: v.tags,
                    nodes_count: v.nodes.length
                })),
                passes: results.passes.length,
                incomplete: results.incomplete.length
            };
        }
    """)
    return results


async def run_keyboard_test(page) -> KeyboardResult:
    """Simula navegação por teclado (Tab) e detecta armadilhas de foco."""
    result = KeyboardResult()

    # Colocar foco na página
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(300)

    visited_elements = []
    max_tabs = 50  # Limite para evitar loop infinito
    trap_threshold = 3  # Se o mesmo elemento receber foco 3x, é armadilha

    for i in range(max_tabs):
        # Capturar elemento com foco atual
        focused = await page.evaluate("""
            () => {
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                return {
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    className: (el.className || '').toString().slice(0, 50),
                    text: (el.textContent || '').slice(0, 30).trim(),
                    role: el.getAttribute('role') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    hasVisibleFocus: (() => {
                        const style = getComputedStyle(el);
                        return style.outlineStyle !== 'none' || 
                               style.boxShadow !== 'none' ||
                               el.matches(':focus-visible');
                    })()
                };
            }
        """)

        if not focused:
            break

        element_id = f"{focused['tag']}#{focused['id']}.{focused['className']}"
        visited_elements.append(element_id)

        if not focused.get('hasVisibleFocus', True):
            result.elements_without_indicator += 1

        # Detectar armadilha de foco
        count = visited_elements.count(element_id)
        if count >= trap_threshold:
            result.focus_traps.append({
                "element": element_id,
                "description": f"Elemento {focused['tag']} prendeu o foco ({count}x)",
                "aria_label": focused.get('ariaLabel', '')
            })
            result.success = False
            break

        # Registrar na sequência
        result.tab_sequence.append({
            "order": i + 1,
            "tag": focused['tag'],
            "role": focused.get('role', ''),
            "label": focused.get('ariaLabel') or focused.get('text', ''),
            "visible_focus": focused.get('hasVisibleFocus', False)
        })

        # Próximo Tab
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(200)

    result.focusable_elements = len(set(visited_elements))
    return result


def classify_violations(raw_violations: list) -> list[Violation]:
    """Classifica violações usando a Matriz de Severidade da pesquisa."""
    violations = []
    for v in raw_violations:
        # Determinar peso de severidade
        impact = v.get("impact", "minor")
        weight = SEVERITY_WEIGHTS.get(impact, 1)

        # Mapear para critério WCAG da pesquisa
        wcag_tags = v.get("tags", [])
        criterion = ""
        for tag in wcag_tags:
            # Extrair número do critério (ex: "wcag111" → "1.1.1")
            if tag.startswith("wcag") and len(tag) >= 7:
                digits = tag[4:]
                if digits.isdigit() and len(digits) >= 3:
                    criterion = f"{digits[0]}.{digits[1]}.{digits[2]}"
                    break

        violations.append(Violation(
            id=v["id"],
            impact=impact,
            description=v["description"],
            help=v["help"],
            help_url=v.get("helpUrl", ""),
            wcag_tags=wcag_tags,
            nodes_count=v.get("nodes_count", 0),
            severity_weight=weight,
            wcag_criterion=criterion
        ))

    return violations


# ═══════════════════════════════════════════════════════
# RELATÓRIO HTML - Gerador com Highcharts
# ═══════════════════════════════════════════════════════

def generate_html_report(report: AuditReport, output_path: str):
    """Gera relatório HTML interativo com dashboard Highcharts."""
    
    # Dados para os gráficos
    violations_by_impact = {
        "Crítica (3)": report.critical_count,
        "Séria (2)": report.serious_count,
        "Moderada (1)": report.moderate_count,
    }

    violations_by_wcag = {}
    for v in report.violations:
        key = WCAG_CRITERIA_MAP.get(v.wcag_criterion, v.wcag_criterion or "Outro")
        violations_by_wcag[key] = violations_by_wcag.get(key, 0) + 1

    # Dados do teste de teclado
    kb_data = ""
    if report.keyboard_result:
        kb = report.keyboard_result
        kb_status = "✅ Aprovado" if kb.success else "❌ Armadilha detectada"
        kb_data = f"""
        <div class="kpi-row">
            <div class="kpi"><div class="kpi-value">{kb.focusable_elements}</div><div class="kpi-label">Elementos Focáveis</div></div>
            <div class="kpi"><div class="kpi-value">{len(kb.focus_traps)}</div><div class="kpi-label">Armadilhas de Foco</div></div>
            <div class="kpi"><div class="kpi-value">{kb.elements_without_indicator}</div><div class="kpi-label">Sem Indicador Visual</div></div>
            <div class="kpi"><div class="kpi-value">{kb_status}</div><div class="kpi-label">Status Teclado</div></div>
        </div>
        """

    # Template HTML
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>AccessHome Analyzer — Relatório</title>
<script src="https://cdn.jsdelivr.net/npm/highcharts@12.1.2/highcharts.js"></script>
<script src="https://cdn.jsdelivr.net/npm/highcharts@12.1.2/modules/accessibility.js"></script>
<style>
:root {{
    --color-bg: #0d1117;
    --color-surface: #161b22;
    --color-border: #30363d;
    --color-text: #e6edf3;
    --color-text-secondary: #8b949e;
    --color-primary: #58a6ff;
    --color-success: #3fb950;
    --color-error: #f85149;
    --color-warning: #d29922;
    --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --font-mono: 'SF Mono', Consolas, monospace;
    --radius-md: 8px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--color-bg); color: var(--color-text); font-family: var(--font-sans); padding: 32px; }}
h1 {{ font-size: 24px; margin-bottom: 4px; }}
.subtitle {{ color: var(--color-text-secondary); font-size: 14px; margin-bottom: 24px; }}
.kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.kpi {{ background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 16px; text-align: center; }}
.kpi-value {{ font-size: 28px; font-weight: 700; font-family: var(--font-mono); }}
.kpi-label {{ font-size: 11px; color: var(--color-text-secondary); text-transform: uppercase; margin-top: 4px; }}
.card {{ background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 20px; margin-bottom: 20px; }}
.card-title {{ font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--color-text-secondary); }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--color-border); }}
th {{ color: var(--color-text-secondary); font-weight: 600; text-transform: uppercase; font-size: 11px; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
.badge-critical {{ background: rgba(248,81,73,0.15); color: var(--color-error); }}
.badge-serious {{ background: rgba(210,153,34,0.15); color: var(--color-warning); }}
.badge-moderate {{ background: rgba(88,166,255,0.15); color: var(--color-primary); }}
footer {{ text-align: center; color: var(--color-text-secondary); font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--color-border); }}
@media (max-width: 768px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<h1>🏠 AccessHome Analyzer — Relatório de Auditoria</h1>
<p class="subtitle">URL: {report.url} | {report.timestamp} | Tempo de scan: {report.scan_time:.1f}s</p>

<div class="kpi-row">
    <div class="kpi"><div class="kpi-value" style="color:var(--color-error)">{report.critical_count}</div><div class="kpi-label">Críticas (Peso 3)</div></div>
    <div class="kpi"><div class="kpi-value" style="color:var(--color-warning)">{report.serious_count}</div><div class="kpi-label">Sérias (Peso 2)</div></div>
    <div class="kpi"><div class="kpi-value" style="color:var(--color-primary)">{report.moderate_count}</div><div class="kpi-label">Moderadas (Peso 1)</div></div>
    <div class="kpi"><div class="kpi-value" style="color:var(--color-success)">{report.passes}</div><div class="kpi-label">Aprovados</div></div>
</div>

{kb_data}

<div class="grid">
    <div class="card">
        <div class="card-title">Violações por Severidade</div>
        <div id="chart-severity" style="height:280px"></div>
    </div>
    <div class="card">
        <div class="card-title">Violações por Critério WCAG</div>
        <div id="chart-wcag" style="height:280px"></div>
    </div>
</div>

<div class="card">
    <div class="card-title">Detalhamento das Violações</div>
    <table>
        <thead><tr><th>ID</th><th>Impacto</th><th>Peso</th><th>Descrição</th><th>Elementos</th><th>WCAG</th></tr></thead>
        <tbody>
"""

    for v in sorted(report.violations, key=lambda x: -x.severity_weight):
        badge_class = "badge-critical" if v.severity_weight == 3 else "badge-serious" if v.severity_weight == 2 else "badge-moderate"
        impact_label = "Crítica" if v.severity_weight == 3 else "Séria" if v.severity_weight == 2 else "Moderada"
        html += f"""<tr>
            <td><code>{v.id}</code></td>
            <td><span class="badge {badge_class}">{impact_label}</span></td>
            <td>{v.severity_weight}</td>
            <td>{v.help}</td>
            <td>{v.nodes_count}</td>
            <td>{v.wcag_criterion or '—'}</td>
        </tr>"""

    html += f"""
        </tbody>
    </table>
</div>

<footer>
    AccessHome Analyzer v1.0 — Yago Santos Silva | Pesquisa PICTA 2026 (Senac SP)<br>
    Baseado nas diretrizes WCAG 2.1 (W3C) e axe-core (Deque Systems)
</footer>

<script>
Highcharts.setOptions({{
    chart: {{ backgroundColor: 'transparent' }},
    title: {{ style: {{ color: '#e6edf3' }} }},
    legend: {{ itemStyle: {{ color: '#8b949e' }} }},
    xAxis: {{ labels: {{ style: {{ color: '#8b949e' }} }}, gridLineColor: '#30363d' }},
    yAxis: {{ labels: {{ style: {{ color: '#8b949e' }} }}, gridLineColor: '#30363d' }},
    credits: {{ enabled: false }}
}});

Highcharts.chart('chart-severity', {{
    chart: {{ type: 'pie' }},
    title: {{ text: null }},
    series: [{{
        name: 'Violações',
        data: [
            {{ name: 'Crítica (Peso 3)', y: {report.critical_count}, color: '#f85149' }},
            {{ name: 'Séria (Peso 2)', y: {report.serious_count}, color: '#d29922' }},
            {{ name: 'Moderada (Peso 1)', y: {report.moderate_count}, color: '#58a6ff' }}
        ]
    }}],
    plotOptions: {{ pie: {{ dataLabels: {{ enabled: true, format: '{{point.name}}: {{point.y}}', style: {{ color: '#e6edf3' }} }} }} }}
}});

Highcharts.chart('chart-wcag', {{
    chart: {{ type: 'bar' }},
    title: {{ text: null }},
    xAxis: {{ categories: {json.dumps(list(violations_by_wcag.keys()))} }},
    yAxis: {{ title: {{ text: 'Violações' }} }},
    series: [{{ name: 'Violações', data: {json.dumps(list(violations_by_wcag.values()))}, color: '#58a6ff' }}],
    legend: {{ enabled: false }},
    plotOptions: {{ bar: {{ borderRadius: 3, dataLabels: {{ enabled: true, style: {{ color: '#e6edf3' }} }} }} }}
}});
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ═══════════════════════════════════════════════════════
# CLI - Interface de Linha de Comando
# ═══════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(
        description="🏠 AccessHome Analyzer — Auditoria de acessibilidade para Smart Homes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python analyzer.py https://demo.home-assistant.io
  python analyzer.py https://demo.home-assistant.io --keyboard
  python analyzer.py https://demo.home-assistant.io --full --output report.html
        """
    )
    parser.add_argument("url", help="URL da interface de Smart Home para auditar")
    parser.add_argument("--keyboard", "-k", action="store_true", help="Executar teste de navegação por teclado")
    parser.add_argument("--full", "-f", action="store_true", help="Auditoria completa (axe + teclado + relatório)")
    parser.add_argument("--output", "-o", default="relatorio_acessibilidade.html", help="Caminho do relatório HTML (padrão: relatorio_acessibilidade.html)")
    parser.add_argument("--screenshot", "-s", action="store_true", help="Capturar screenshot da página")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Timeout em segundos (padrão: 30)")
    parser.add_argument("--headless", action="store_true", default=True, help="Executar em modo headless (padrão: True)")
    parser.add_argument("--no-headless", action="store_true", help="Mostrar o navegador durante o scan")

    args = parser.parse_args()

    if args.full:
        args.keyboard = True

    headless = not args.no_headless

    # Banner
    console.print(Panel.fit(
        "[bold cyan]AccessHome Analyzer v1.0[/bold cyan]\n"
        "[dim]Auditoria de Acessibilidade — Smart Home[/dim]",
        border_style="cyan"
    ))
    console.print(f"\n🔍 [bold]Alvo:[/bold] {args.url}")
    console.print(f"⚙️  [dim]Modo: {'Completo' if args.full else 'Axe + Teclado' if args.keyboard else 'Axe apenas'}[/dim]\n")

    report = AuditReport(
        url=args.url,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="AccessHomeAnalyzer/1.0 (Research; PICTA-2026)"
        )
        page = await context.new_page()

        # Navegar
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("Carregando página...", total=None)

            try:
                await page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                await page.wait_for_timeout(3000)  # Aguardar renderização JS
            except Exception as e:
                console.print(f"\n[red]❌ Erro ao acessar URL: {e}[/red]")
                await browser.close()
                sys.exit(1)

            progress.update(task, description="Executando auditoria axe-core...")

            import time
            start = time.time()

            # Auditoria axe-core
            try:
                axe_results = await run_axe_audit(page)
                report.violations = classify_violations(axe_results["violations"])
                report.passes = axe_results["passes"]
                report.incomplete = axe_results["incomplete"]
            except Exception as e:
                console.print(f"\n[red]❌ Erro na auditoria axe-core: {e}[/red]")
                await browser.close()
                sys.exit(1)

            # Teste de teclado
            if args.keyboard:
                progress.update(task, description="Testando navegação por teclado...")
                try:
                    report.keyboard_result = await run_keyboard_test(page)
                except Exception as e:
                    console.print(f"\n[yellow]⚠️ Erro no teste de teclado: {e}[/yellow]")

            # Screenshot
            if args.screenshot:
                progress.update(task, description="Capturando screenshot...")
                screenshot_path = args.output.replace(".html", "_screenshot.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                report.screenshot_path = screenshot_path

            report.scan_time = time.time() - start
            progress.update(task, description="[green]✅ Scan completo!")

        await browser.close()

    # Exibir resultados no terminal
    console.print(f"\n⏱️  Tempo de scan: [bold]{report.scan_time:.1f}s[/bold]\n")

    # Tabela de resumo
    table = Table(title="📋 RESULTADOS", show_header=True, header_style="bold cyan")
    table.add_column("Categoria", style="dim")
    table.add_column("Quantidade", justify="right")
    table.add_column("Peso", justify="center")

    table.add_row("Violações Críticas", str(report.critical_count), "[red]3[/red]")
    table.add_row("Violações Sérias", str(report.serious_count), "[yellow]2[/yellow]")
    table.add_row("Violações Moderadas", str(report.moderate_count), "[blue]1[/blue]")
    table.add_row("Aprovados", str(report.passes), "[green]0[/green]")

    console.print(table)

    # Teste de teclado
    if report.keyboard_result:
        kb = report.keyboard_result
        console.print(f"\n⌨️  [bold]TESTE DE TECLADO:[/bold]")
        console.print(f"  ├─ Elementos focáveis: {kb.focusable_elements}")
        console.print(f"  ├─ Armadilhas de foco: {len(kb.focus_traps)}")
        console.print(f"  └─ Sem indicador visual: {kb.elements_without_indicator}")
        if not kb.success:
            console.print(f"  [red]⚠️ ARMADILHA DETECTADA![/red]")

    # Gerar relatório HTML
    generate_html_report(report, args.output)
    console.print(f"\n📄 [bold green]Relatório salvo:[/bold green] {args.output}")

    # Código de saída
    if report.critical_count > 0:
        console.print(f"\n[red]⚠️ {report.critical_count} violações CRÍTICAS encontradas — interface INACESSÍVEL[/red]")
        sys.exit(2)
    elif report.serious_count > 0:
        console.print(f"\n[yellow]⚠️ {report.serious_count} violações sérias — acessibilidade comprometida[/yellow]")
        sys.exit(1)
    else:
        console.print(f"\n[green]✅ Nenhuma violação crítica ou séria encontrada![/green]")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
