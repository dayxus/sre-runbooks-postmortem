---
title: Runbook template (validated by machine)
description: Estrutura obrigatória de um runbook deste repositório.
---

# Runbook template

Todo runbook deste repositório é validado por `sretriage check-runbooks`. O
template abaixo é a razão de existir do projeto: copy, preencha, rode o lint.

## Front matter obrigatório

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

Regras do front matter:

- `id`: kebab-case, único na biblioteca, prefixado pela área (`k8s`, `cloud`, `obs`, `db`, `cicd`, `net`).
- `severity`: um de `critical`, `high`, `medium`, `low`.
- `slo_impact`: um de `availability`, `latency`, `error-rate`, `throughput`, `freshness`, `durability`, `cost`.
- `last_reviewed`: `YYYY-MM-DD`, nunca no futuro. Acima de 180 dias entra em `reports/stale-runbooks.md`.
- `owner`: time genérico responsável (`platform`, `data-platform`, `observability`).

## Seções obrigatórias, nesta ordem

1. `## Sintomas` — o que se observa de fora, em bullets.
2. `## Impacto no SLO` — qual indicador cai e como o error budget é consumido.
3. `## Detecção` — a linha `**Alerta:** \`NomeDoAlerta\`` e a expressão PromQL/log query.
4. `## Diagnóstico` — passos numerados, cada um com bloco de comando com linguagem declarada e tempo esperado.
5. `## Mitigação` — ação imediata, com `**Risco:**` declarado e comandos.
6. `## Escalonamento` — quando acionar o time de plantão do serviço e o de plataforma.
7. `## Verificação` — como provar que resolveu, com comando.
8. `## Prevenção` — o que impede a repetição.
9. `## Referências` — links externos que a auditoria semanal verifica.

## Exemplo mínimo de seção de diagnóstico

```bash
kubectl -n prod describe pod checkout-api-7d9c8f6b5-x4ltq | sed -n '/Last State/,/Events/p'
```

Esperado: `Reason: OOMKilled`. Tempo: ~20 s.

## O que o lint rejeita

| Regra | Motivo |
| --- | --- |
| Seção obrigatória ausente ou fora de ordem | A pessoa lê no incidente, com pressa |
| Bloco de código sem linguagem | Comando impreciso vira comando copiado errado |
| `Diagnóstico` sem passo numerado | Ninguém segue parágrafo no meio do incidente |
| `Mitigação` sem risco declarado | Ação de contenção tem efeito colateral |
| `Escalonamento` sem plantão | Sem dono, o incidente fica sem decisão |
| `last_reviewed` inválido ou no futuro | Revisão é compromisso verificável |
| Token de placeholder (`TODO`, `TBD`, `FIXME`) | Runbook inacabado não é runbook |
| Link relativo quebrado | Runbook órfão é runbook morto |
