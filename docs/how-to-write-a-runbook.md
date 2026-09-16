# Como escrever um runbook que sobrevive ao incidente

Um runbook é lido por alguém cansado, às 3 da manhã, sem contexto além do
alerta. Escreva para essa pessoa.

## A regra central

Cada passo precisa ser executável sem pensar e verificável sem interpretação. Se
o passo é "verifique os logs", ele não é um passo — é uma tarefa de casa.

| Ruim | Bom |
| --- | --- |
| "Verifique os logs do pod" | `kubectl -n prod logs deploy/checkout-api --previous --tail=80` procurando `OOMKilled` |
| "Analise a latência" | `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{service="checkout-api"}[5m])))` |
| "Escalone se necessário" | "Acione o time de plantão do serviço se houver usuário afetado; plataforma se o nó estiver envolvido" |

## Estrutura

Use `templates/runbook-template.md`. As nove seções são obrigatórias e validadas
por `sretriage check-runbooks`:

1. **Sintomas** — o que se observa de fora, em bullets, na linguagem de quem recebe o alerta.
2. **Impacto no SLO** — qual indicador cai e como o error budget é consumido. Ajuda a decidir urgência.
3. **Detecção** — o nome do alerta e a expressão que dispara. Sem isso, não se sabe qual sinal é confiável.
4. **Diagnóstico** — passos numerados, comandos copiáveis, tempo esperado por passo.
5. **Mitigação** — ação imediata com o risco declarado. Mitigação sem risco declarado é armadilha.
6. **Escalonamento** — quando escalar e para quem, de forma genérica o suficiente para sobreviver a mudança de time.
7. **Verificação** — como provar que resolveu, com comando. Contenção sem verificação vira incidente reaberto.
8. **Prevenção** — o que impede a repetição. É a ponte para o postmortem.
9. **Referências** — links externos, auditados semanalmente pelo workflow de manutenção.

## Front matter

```yaml
---
id: k8s-crashloopbackoff
title: CrashLoopBackOff em workload de produção
severity: high
services: [kubernetes]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---
```

`severity` define quem acorda. `slo_impact` liga o runbook ao indicador que ele
protege. `last_reviewed` é a data da última revisão **efetiva** — não a data do
último commit. O workflow semanal cobra revisão acima de 180 dias.

## Escrevendo o diagnóstico

1. Comece pelo comando mais barato que separa as hipóteses mais prováveis.
2. Cada passo deve dizer o que se espera ver, não apenas o que rodar.
3. Coloque o tempo esperado. Quem está no incidente precisa saber se travou.
4. Nunca peça para "olhar tudo": a pessoa não sabe o que é relevante.
5. Termine o diagnóstico com uma decisão explícita: ir para mitigar ou escalar.

## Escrevendo a mitigação

- A primeira mitigação deve ser reversível e de baixo risco.
- Declare o risco de cada ação: **Risco:** o que pode piorar.
- Prefira reduzir impacto a corrigir causa durante o incidente.
- Nada de ação destrutiva sem antes checar redundância (PDB, réplicas, backup).

## Escrevendo a verificação

Um comando que prova a recuperação é obrigatório. "Parece que voltou" não é
verificação. Quando possível, verifique o efeito no usuário (uma requisição real
no fluxo) e não apenas o estado interno.

## Manutenção

- Revise a cada 180 dias ou depois de qualquer incidente que use o runbook.
- Ensaios (game days) encontram passos quebrados melhor do que leitura.
- O CI rejeita seção ausente, comando sem linguagem declarada e link relativo quebrado.
- Rode o runbook contra um ambiente de laboratório antes de confiar nele em produção.
