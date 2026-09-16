---
id: obs-alert-fatigue
title: Fadiga de alertas com ruído acima do sinal
severity: medium
services: [observability]
slo_impact: cost
last_reviewed: 2026-09-15
owner: observability
---

# Fadiga de alertas com ruído acima do sinal

Pessoas param de olhar o canal de plantão porque quase todo alerta é ruído. O
custo aparece depois: um incidente real passa batido em meio a 40 notificações
na madrugada.

## Sintomas

- Mais de 5 alertas por plantão sem ação tomada, ou alerta que se resolve sozinho em minutos.
- Silenciamentos permanentes acumulados (`silences` sem expiração).
- Plantão com medo de silenciar alertas importantes por não distinguir do ruído.
- O mesmo alerta dispara para vários sintomas de uma única causa raiz.

## Impacto no SLO

Fadiga não queima error budget diretamente — queima a capacidade de reação.
Indicadores: tempo de reconhecimento subindo, MTTA piorando, incidentes detectados
por usuário em vez de por monitoramento. Isso é custo operacional (`cost`) e
precursor de indisponibilidade.

## Detecção

**Alerta:** `AlertNoiseRatio`

```promql
sum(increase(alerts_fired_total[7d]))
  / sum(increase(alerts_actioned_total[7d])) > 5
```

**Alerta:** `AutoResolvedAlerts`

```promql
sum(increase(alertmanager_alerts_resolved_total{resolution="auto"}[7d]))
  / sum(increase(alertmanager_alerts_total[7d])) > 0.7
```

## Diagnóstico

1. Liste os alertas mais frequentes da semana, por nome e serviço.

   ```bash
   curl -sS 'http://localhost:9090/api/v1/query?query=topk(10,sum%20by%20(alertname,service)(increase(alerts_fired_total%5B7d%5D)))' | head -40
   ```

   Tempo: ~10 s.

2. Classifique cada um: página (acorda alguém), ticket (dia útil) ou log (nunca deve notificar).

   ```bash
   kubectl -n observability get prometheusrule -o jsonpath='{.items[*].spec.groups[*].rules[*].alert}{"\n"}' | tr ' ' '\n' | sort | uniq -c | sort -rn | head -20
   ```

   Tempo: ~15 s.

3. Meça quanto tempo cada alerta leva para se resolver sem intervenção.

   ```bash
   curl -sS 'http://localhost:9090/api/v1/query?query=avg%20by%20(alertname)(hole_until_resolve_seconds)' | head -30
   ```

   Alerta que se resolve sozinho em menos de 10 minutos é candidato a virar baixa severidade. Tempo: ~10 s.

4. Verifique se os alertas usam janelas e `for` adequados (pico de 1 minuto não é incidente).

   ```bash
   kubectl -n observability get prometheusrule checkout-api-alerts -o yaml | grep -A4 -Ei 'alert:|for:'
   ```

   Tempo: ~10 s.

5. Cruze alertas que disparam juntos para achar grupo (inhibition) mal configurado.

   ```bash
   kubectl -n observability get alertmanager main -o jsonpath='{.spec.inhibitRules}{"\n"}'
   ```

   Tempo: ~15 s.

6. Verifique o que o plantão realmente responde e a que horas.

   ```bash
   curl -sS http://localhost:9093/api/v2/alerts | head -40
   ```

   Tempo: ~15 s.

## Mitigação

**Risco:** silenciar para reduzir ruído esconde o problema real; todo silêncio
precisa de prazo e de um responsável nomeado, com chamado aberto.

1. Rebaixe para ticket os alertas que se resolvem sozinhos e não exigem ação imediata.

   ```yaml
   route:
     receiver: ticket-queue
     matchers:
       - severity="warning"
   ```

2. Ajuste janela e `for` dos alertas sintomáticos que oscilam.

   ```bash
   kubectl -n observability patch prometheusrule checkout-api-alerts --type=json \
     -p '[{"op":"replace","path":"/spec/groups/0/rules/0/for","value":"15m"}]'
   ```

3. Agrupe a causa raiz: mantenha o alerta de disponibilidade e transforme os sintomas derivados em anotação do mesmo incidente.

   ```bash
   kubectl -n observability get prometheusrule checkout-api-alerts -o jsonpath='{.spec.groups[*].name}{"\n"}'
   ```

4. Aplique silêncio com prazo curto durante a limpeza e registre o horário de fim.

   ```bash
   amtool silence add alertname=HighLatencyP95 --duration=2h --comment="limpeza de ruido - revisao em 2h"
   ```

## Escalonamento

- Acione o time de plantão de observabilidade quando o ruído vier de regra compartilhada ou de configuração do Alertmanager.
- Acione o time de plantão do serviço quando o alerta for específico de um workload e precisar de mudança de threshold lá.
- Leve para a revisão semanal de confiabilidade quando a limpeza exigir decisão de política (o que pode acordar alguém).

## Verificação

1. Número de alertas por plantão caiu e a razão alerta/ação ficou abaixo de 2.

   ```promql
   sum(increase(alerts_fired_total[7d])) / sum(increase(alerts_actioned_total[7d]))
   ```

2. Nenhum silenciamento sem expiração ficou para trás.

   ```bash
   amtool silence query | grep -Ei 'expiresAt|comment' | head -20
   ```

3. Todo alerta remanescente tem ação esperada escrita na anotação `runbook_url` e `description`.

## Prevenção

- Revise alertas disparados na semana a cada plantão; apague o que ninguém agiu duas vezes.
- Cada alerta precisa de `runbook_url` apontando para o runbook que o resolve.
- Alertas devem ser sintomáticos (usuário sente) com causa como contexto, não o contrário.
- Orce o número de páginas por plantão e trate excesso como bug de configuração.

## Referências

- [Google SRE Workbook: alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Google SRE Book: being on-call](https://sre.google/sre-book/being-on-call/)
- [Prometheus: alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus: alerting practices](https://prometheus.io/docs/practices/alerting/)
