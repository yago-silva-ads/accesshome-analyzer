# 🏠 AccessHome Analyzer

> Ferramenta automatizada de auditoria de acessibilidade para interfaces de Smart Home.  
> Desenvolvido por Yago Santos Silva — Pesquisa PICTA 2026 (Senac SP)

## 🎯 O que faz

1. **Abre qualquer interface web** de Smart Home (Home Assistant, openHAB, SharpTools, etc.)
2. **Executa auditoria axe-core** — detecta violações WCAG 2.1 (Níveis A e AA)
3. **Testa navegação por teclado** — simula Tab e verifica armadilhas de foco
4. **Classifica severidade** — usa a Matriz de Severidade da pesquisa (Pesos 0-3)
5. **Gera relatório HTML interativo** — dashboard com gráficos Highcharts

## 🛠️ Tecnologias

| Componente | Tecnologia |
|---|---|
| Motor de varredura | Playwright (headless Chromium) |
| Auditoria WCAG | axe-core (injetado via JS) |
| Teste de teclado | Playwright keyboard simulation |
| Classificação | Python (algoritmo próprio baseado na Matriz de Severidade) |
| Relatório | HTML + Highcharts (gerado automaticamente) |
| CLI | Python argparse |

## 📦 Instalação

```bash
# Clonar o projeto
git clone https://github.com/yago-silva-ads/accesshome-analyzer.git
cd accesshome-analyzer

# Criar virtualenv
python -m venv .venv
.venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt

# Instalar browsers do Playwright
playwright install chromium
```

## 🚀 Uso

```bash
# Scan básico
python analyzer.py https://demo.home-assistant.io

# Scan com teste de teclado
python analyzer.py https://demo.home-assistant.io --keyboard

# Scan completo (auditoria + teclado + relatório)
python analyzer.py https://demo.home-assistant.io --full --output relatorio.html
```

## 📊 Exemplo de Saída

```
╔══════════════════════════════════════════════════════╗
║  AccessHome Analyzer v1.0                           ║
║  Auditoria de Acessibilidade - Smart Home           ║
╚══════════════════════════════════════════════════════╝

🔍 Alvo: https://demo.home-assistant.io
⏱️  Tempo de scan: 4.2s

📋 RESULTADOS:
  ├─ Violações Críticas (Peso 3): 9
  ├─ Violações Sérias (Peso 2):   15
  ├─ Violações Moderadas (Peso 1): 0
  └─ Aprovados (Peso 0):           2

⌨️  TESTE DE TECLADO:
  ├─ Elementos focáveis: 23
  ├─ Armadilhas de foco: 0
  └─ Elementos sem indicador visual: 5

📄 Relatório salvo: relatorio.html
```

## 🏗️ Arquitetura (Visão AWS)

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  CLI Local  │────▶│  AWS Lambda      │────▶│  S3 (Relatórios)│
│  (Python)   │     │  (Scan Engine)   │     │                 │
└─────────────┘     └──────────────────┘     └─────────────────┘
                           │                          │
                    ┌──────▼──────┐            ┌──────▼──────┐
                    │  DynamoDB   │            │  CloudFront │
                    │  (Histórico)│            │  (Dashboard)│
                    └─────────────┘            └─────────────┘
```

## 📚 Base Científica

Este software é parte da pesquisa:  
**"Análise de Ferramentas Automatizadas para Testes de Acessibilidade em Interfaces de Smart Home para Usuários com Deficiência Visual"**  
PICTA — Programa de Iniciação Científica e Tecnológica Aplicada (Senac SP, 2026)

## 📄 Licença

MIT License — Uso livre para fins acadêmicos e comerciais.
