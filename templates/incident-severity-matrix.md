---
title: Incident severity matrix
description: Critérios objetivos para classificar severidade, decidir quem paga o custo da resposta e quando abrir postmortem.
tags: [incident-management, severity, on-call]
---

# Matriz de severidade de incidente

Severidade define quanto do time para de trabalhar no que estava fazendo. A
classificação precisa ser objetiva: se duas pessoas discordam, os critérios estão vagos.

## Matriz

| Severidade | Critério (qualquer um) | Resposta esperada | Comunicação | Postmortem |
| --- | --- | --- | --- | --- |
| `crítica` | SLO de nível 1 violado com impacto em usuário final; indisponibilidade total de um serviço externo; perda de dados | Imediata, 24x7, com quem estiver de plantão e escalonamento em 15 min | Canal de incidente dedicado, atualização a cada 30 min, aviso a liderança | Obrigatório em até 5 dias úteis |
| `alta` | Degradação relevante de um serviço de nível 1 sem indisponibilidade total; SLO violando de forma sustentada; falha de região secundária | Imediata em horário comercial, plantão acionado fora dele | Canal de incidente, atualização a cada 1 hora | Obrigatório em até 10 dias úteis |
| `média` | Serviço interno com degradação; risco declarado de virar `alta`; error budget queimando acima do normal sem impacto direto | Próximo horário comercial, tratado como prioridade sobre trabalho planejado | Registro no canal do time | Opcional, recomendado se houver recorrência |
| `baixa` | Ruído operacional, alerta impreciso, dívida de observabilidade, documentação incorreta | Backlog priorizado, tratado como trabalho normal | Registro em ticket | Não |

## Como decidir a severidade em 60 segundos

1. Tem usuário final impactado agora? Sim → no mínimo `alta`.
2. Houve indisponibilidade total ou perda de dados? Sim → `crítica`.
3. Existe risco de perda de dados ou de corrupção silenciosa? Sim → `crítica`.
4. O impacto pode crescer sozinho nas próximas horas? Sim → no mínimo `alta`.
5. Sem impacto externo e sem tendência de piora → `média` ou `baixa`.

## Reclassificação

- Severidade pode subir a qualquer momento; quem está respondendo decide e comunica.
- Severidade só desce com justificativa explícita: "o erro não cresce mais, a
  contenção está estável e o error budget parou de queimar".
- Reclassificar sem comunicar é o erro mais comum: cria confusão sobre quem precisa acordar.

## Donos por fase

| Fase | Dono | Responsabilidade |
| --- | --- | --- |
| Detecção | monitoramento | alerta sintomático com `runbook_url` |
| Resposta | time de plantão do serviço | contenção, comunicação e decisão de escalonamento |
| Escalonamento | time de plantão de plataforma | dependências de infraestrutura |
| Investigação | quem respondeu + par do time | análise de causa, não de culpa |
| Postmortem | um autor nomeado | documento, action items e follow-up |
| Follow-up | dono de cada action item | prazo e critério de verificação |

## Exemplos de classificação

| Situação | Severidade | Por quê |
| --- | --- | --- |
| Taxa de erro de 40% no checkout por 20 minutos | `crítica` | usuário final impedido de completar pedido, SLO de nível 1 violado |
| Latência p95 dobrada sem erro visível em serviço de nível 1 | `alta` | degradação relevante e risco de escalar |
| Fila de processamento de relatórios 3 horas atrasada | `média` | sem impacto em transação, `freshness` degradado |
| 7 alertas de ruído no plantão da madrugada | `baixa` | custo operacional sem impacto direto |
| Um dos três nós de um cluster fora, capacidade suficiente | `alta` | redundância reduzida com risco declarado |

## Anti-padrões

- Classificar por quem reclamou, não pelo impacto medido.
- Manter `crítica` por 8 horas depois de contida, esgotando o time por inércia.
- Ignorar incidente sem reclamação externa que queima error budget.
- Abrir postmortem e deixar action items sem dono.
