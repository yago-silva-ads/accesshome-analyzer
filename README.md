# AccessHome Analyzer

Ferramenta automatizada de auditoria de acessibilidade para interfaces de Smart Home.

Desenvolvido por Yago Santos Silva como parte da pesquisa PICTA 2026 (Senac SP):
*"Análise de Ferramentas Automatizadas para Testes de Acessibilidade em Interfaces de Smart Home para Usuários com Deficiência Visual"*.

---

## Sobre

O AccessHome Analyzer integra auditoria automatizada WCAG 2.1 e simulação de navegação por teclado em uma única solução, eliminando a necessidade de operar múltiplas ferramentas isoladamente. A ferramenta foi projetada para avaliar interfaces web de plataformas de automação residencial (Home Assistant, openHAB, SharpTools, entre outras).

### Funcionalidades

1. Abre qualquer interface web de Smart Home via navegador headless
2. Executa auditoria axe-core com detecção de violações WCAG 2.1 (Níveis A e AA)
3. Simula navegação por teclado (Tab) e identifica armadilhas de foco
4. Classifica cada violação segundo a Matriz de Severidade da pesquisa (Pesos 0 a 3)
5. Gera relatório HTML interativo com gráficos Highcharts

---

## Tecnologias

| Componente           | Tecnologia                                              |
|----------------------|---------------------------------------------------------|
| Motor de varredura   | Playwright (headless Chromium)                          |
| Auditoria WCAG       | axe-core (injetado via JavaScript no DOM)               |
| Teste de teclado     | Playwright keyboard simulation                          |
| Classificação        | Python (algoritmo baseado na Matriz de Severidade)      |
| Relatório            | HTML + Highcharts                                       |
| CLI                  | Python argparse                                         |

---

## Instalação

```bash
git clone https://github.com/yago-silva-ads/accesshome-analyzer.git
cd accesshome-analyzer

python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

pip install -r requirements.txt
playwright install chromium
```

---

## Uso

```bash
# Scan básico
python analyzer.py https://demo.home-assistant.io

# Scan com teste de teclado
python analyzer.py https://demo.home-assistant.io --keyboard

# Scan completo (auditoria + teclado + relatório)
python analyzer.py https://demo.home-assistant.io --full --output relatorio.html
```

### Exemplo de saída

```
AccessHome Analyzer v1.0
Auditoria de Acessibilidade - Smart Home

Alvo: https://demo.home-assistant.io
Tempo de scan: 4.2s

RESULTADOS:
  Violações Críticas (Peso 3): 9
  Violações Sérias (Peso 2):   15
  Violações Moderadas (Peso 1): 0
  Aprovados (Peso 0):           2

TESTE DE TECLADO:
  Elementos focáveis: 23
  Armadilhas de foco: 0
  Elementos sem indicador visual: 5

Relatório salvo: relatorio.html
```

---

## Dashboard

Os resultados consolidados da pesquisa estão disponíveis em um dashboard interativo:

**https://yago-silva-ads.github.io/accesshome-analyzer/**

O dashboard apresenta:
- Distribuição de violações por severidade e plataforma
- Comparativo de efetividade entre Lighthouse, Axe DevTools, WAVE e NVDA
- Mapa de calor dos critérios WCAG por plataforma
- Pontuações Lighthouse por plataforma

---

## Arquitetura

```
CLI (Python)  -->  Playwright (Chromium headless)  -->  axe-core (auditoria WCAG)
                          |                                     |
                   Keyboard Sim                          Classificação
                   (Tab, foco)                          (Matriz Severidade)
                          |                                     |
                          +----------> Relatório HTML <---------+
                                       (Highcharts)
```

---

## Base científica

Este software é parte integrante da pesquisa:

> SILVA, Y. S. **Análise de Ferramentas Automatizadas para Testes de Acessibilidade em Interfaces de Smart Home para Usuários com Deficiência Visual**. 2026. Programa de Iniciação Científica e Tecnológica Aplicada (PICTA) -- Senac São Paulo.

A pesquisa avaliou três plataformas (Home Assistant, openHAB e SharpTools) utilizando Lighthouse, Axe DevTools, WAVE e validação manual com NVDA. Os resultados demonstram que ferramentas automatizadas são necessárias como filtro primário, porém insuficientes para atestar a acessibilidade real das interfaces.

---

## Licença

MIT License -- Uso livre para fins acadêmicos e comerciais.
