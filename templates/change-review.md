---
title: Change review checklist
description: Revisão de mudança em produção, com foco em reversibilidade, risco medido e critério de abortar o rollout.
tags: [change-management, deploy, risk]
---

# Checklist de revisão de mudança

Mudança é a principal causa de incidente em produção e, ao mesmo tempo, a única
forma de melhorar. O objetivo desta revisão não é impedir a mudança, é garantir
que ela seja reversível e observável.

## Obrigatório antes do merge

- [ ] O diff tem um propósito declarado em uma frase (e o PR não mistura dois assuntos).
- [ ] Existe teste automatizado que falha se a mudança for revertida por engano.
- [ ] Migração de banco é compatível para trás (expand/contract) ou tem janela declarada.
- [ ] Configuração nova tem validação e valor padrão seguro.
- [ ] Nenhum segredo, chave ou credencial entrou no repositório.
- [ ] Feature flag existe se o comportamento novo puder ser desligado.
- [ ] O rollback é um comando conhecido e testado, escrito no PR.

## Observabilidade obrigatória

- [ ] A mudança emite métrica, log estruturado ou evento de auditoria para o fluxo afetado.
- [ ] Painel existente permite comparar antes e depois da mudança (dimensão de revisão/versão).
- [ ] Existe alerta que detecta a falha desta mudança, ou a ausência dele está justificada por escrito.
- [ ] O `runbook_url` do alerta aponta para um runbook que passa no lint.

## Risco e reversibilidade

| Pergunta | Se a resposta for "não" |
| --- | --- |
| A mudança pode ser desligada em menos de 5 minutos? | Exija feature flag |
| O estado gravado é compatível com a versão anterior? | Faça expand/contract em dois deploys |
| O impacto é limitado a uma fração do tráfego? | Use canário antes do rollout completo |
| O time de plantão sabe o que fazer se falhar? | Escreva ou atualize o runbook antes |

## Plano de rollout

1. Canário com 1 a 5% do tráfego por pelo menos 30 minutos.
2. Comparar erro e latência do canário contra a versão estável, com o mesmo volume.
3. Critério objetivo de abortar: erro do canário acima do dobro do estável, ou p95 acima de 1,5x por 10 minutos.
4. Rollout progressivo (25%, 50%, 100%) com observação entre etapas.
5. Congelar outras mudanças no mesmo serviço durante a janela.

## Critério de abortar o rollout

```bash
kubectl -n prod rollout undo deploy/checkout-api
kubectl -n prod rollout status deploy/checkout-api --timeout=180s
```

Aborte sem hesitar quando o canário apresentar piora sustentada. Investigar a
causa com o incidente contido é mais barato do que investigar com usuário afetado.

## Depois do rollout

- [ ] Comparativo de SLO antes/depois anexado ao PR, com janela de 24 horas.
- [ ] Flags temporárias agendadas para remoção com prazo e dono.
- [ ] Documentação e runbooks atualizados se o comportamento operacional mudou.
- [ ] Nenhum alerta silenciado temporariamente ficou para trás.

## Anti-padrões

- Aprovar mudança grande "porque o autor é experiente".
- Rollout de 100% direto porque "o ambiente de teste passou".
- Migração destrutiva no mesmo deploy que altera o código que a usa.
- Deixar feature flag ligada para sempre: com o tempo ela deixa de ser um controle de risco.
