# 🏗️ Arquitetura AWS — AccessHome Analyzer

## Visão Geral

```
┌────────────────┐        ┌─────────────────────┐        ┌────────────────┐
│   Frontend     │  HTTP   │   API Gateway       │  Invoke│   Lambda       │
│   (Dashboard)  │───────▶│   /api/scan          │───────▶│   scan_handler │
│   S3+CloudFront│        │   /api/history       │        │   (Python 3.12)│
└────────────────┘        └─────────────────────┘        └───────┬────────┘
                                                                  │
                          ┌───────────────────────────────────────┼────────────────┐
                          │                                       │                │
                    ┌─────▼─────┐                          ┌──────▼─────┐   ┌──────▼──────┐
                    │  DynamoDB  │                          │     S3     │   │  EventBridge│
                    │  scans     │                          │  reports/  │   │  (cron)     │
                    │  history   │                          │  *.html    │   │  scheduled  │
                    └───────────┘                          └────────────┘   └─────────────┘

```

## Componentes

| Serviço | Função | Free Tier |
| --- | --- | --- |
| **API Gateway** (REST) | Endpoint público `/api/scan` e `/api/history` | 1M chamadas/mês |
| **Lambda** (Python 3.12) | Executa axe-core scan via Playwright Layer | 1M invocações/mês |
| **DynamoDB** | Armazena histórico de scans (por URL + timestamp) | 25GB + 25 WCU/RCU |
| **S3** | Hospeda relatórios HTML e o frontend dashboard | 5GB |
| **CloudFront** | CDN para o dashboard estático | 1TB transfer |
| **EventBridge** | Agenda scans recorrentes (monitoring) | Gratuito |

## Custos Estimados

Para uso acadêmico (< 100 scans/mês): **$0.00** (tudo dentro do Free Tier)

## Endpoints da API

```
POST /api/scan
Body: { "url": "https://demo.home-assistant.io", "keyboard_test": true }
Response: { "scan_id": "uuid", "status": "completed", "report_url": "https://..." }

GET /api/history?url=https://demo.home-assistant.io
Response: { "scans": [...], "trend": { "improving": false, "violations_delta": +2 } }

GET /api/report/{scan_id}
Response: Redirect → S3 presigned URL do relatório HTML

```

