---
title: Postmortem template (blameless)
description: Estrutura para conduzir o postmortem de um incidente, focada em causa sistêmica e action items verificáveis.
tags: [postmortem, incident-management, rca]
---

# Postmortem — Degradação do checkout após deploy com configuração inválida

Este arquivo é o template preenchido com um incidente de exemplo. Copie a
estrutura, não o conteúdo: os números abaixo são de um caso fictício de laboratório.

## Metadados

| Campo | Valor |
| --- | --- |
| Incidente | `INC-142` |
| Severidade | `crítica` / `alta` / `média` / `baixa` |
| Início (UTC) | `2026-09-15T00:00Z` |
| Detecção (UTC) | `2026-09-15T00:05Z` |
| Mitigação (UTC) | `2026-09-15T00:40Z` |
| Resolução (UTC) | `2026-09-15T01:10Z` |
| Tempo até detecção (MTTD) | 5 min |
| Tempo até mitigação (MTTM) | 40 min |
| Tempo total | 70 min |
| Error budget consumido | X% da janela de 30 dias |
| Autores | quem respondeu ao incidente |
| Revisores | um par que não participou da resposta |

## Resumo

Duas a quatro linhas, sem jargão, que qualquer pessoa da empresa entende. O que
parou de funcionar, para quem, por quanto tempo, e qual foi a causa sistêmica.

## Impacto

- **Usuários afetados:** número absoluto e proporção.
- **SLOs violados:** nome do SLI, valor observado e o objetivo.
- **Error budget consumido:** percentual da janela e saldo restante.
- **Impacto financeiro ou contratual:** quando aplicável, com a fonte do número.
- **Escopo:** serviços, regiões e fluxos afetados.

## Linha do tempo

| Hora (UTC) | Evento | Fonte |
| --- | --- | --- |
| 00:00 | Deploy concluído no cluster de produção | pipeline |
| 00:03 | Taxa de erro do serviço começa a subir | painel |
| 00:05 | Alerta de SLO dispara e pagina o plantão | Alertmanager |
| 00:12 | Plantão identifica a correlação com o deploy | investigação |
| 00:40 | Rollback concluído, erro volta ao patamar | kubectl |
| 01:10 | Migração reconciliada e incidente encerrado | verificação |

## Detecção

Como o incidente foi percebido, com o que falhou primeiro. Se a detecção veio de
reclamação de usuário em vez de alerta, esse é o achado mais importante do documento.

## Análise da causa

Registre as causas contribuintes, não um único culpado. Use a estrutura:

- **Gatilho:** o evento imediato (deploy, pico, falha de dependência).
- **Causas contribuintes:** condições que permitiram o gatilho virar incidente.
- **Fatores latentes:** decisões antigas que aumentaram o impacto.

### Cinco porquês

1. Por que o serviço devolveu erro? Porque a instância nova não subiu.
2. Por que não subiu? Porque a variável de ambiente obrigatória estava ausente.
3. Por que a variável estava ausente? Porque o manifesto veio de um template desatualizado.
4. Por que o template desatualizado foi aceito? Porque a pipeline não valida chaves obrigatórias.
5. Por que a pipeline não valida? Porque a validação de configuração nunca foi priorizada.

## O que funcionou bem

- Detecção em 5 minutos pelo alerta de SLO, não por reclamação.
- Rollback documentado e ensaiado, executado pelo plantão sem escalar.
- Canal de incidente com escrivão, evitando investigação paralela duplicada.

## O que dificultou a resposta

- Painel sem a dimensão de revisão de deploy, obrigando consulta manual ao histórico.
- Falta de acesso do plantão ao console de dados, exigindo acionar um segundo time.
- Documentação de migração incompleta para o caminho de rollback.

## Action items

| # | Ação | Tipo | Dono | Prazo | Verificação |
| --- | --- | --- | --- | --- | --- |
| 1 | Validar chaves obrigatórias de configuração na pipeline | preventivo | dev | 2026-09-30 | job vermelho com config inválida |
| 2 | Adicionar dimensão de revisão nos painéis de erro | detecção | observability | 2026-09-25 | gráfico mostra a revisão |
| 3 | Ensaiar rollback com migração aplicada | resposta | platform | 2026-10-10 | relatório de ensaio |
| 4 | Documentar procedimento de reconciliação de dados | resposta | data-platform | 2026-10-05 | runbook publicado e lintado |

Cada ação precisa de dono, prazo e critério de verificação. Ação sem dono não é
ação, é intenção.

## O que não entra neste documento

- Nome de pessoa como causa ("fulano errou no deploy").
- Justificativa defensiva ou narrativa de culpa.
- Métrica inventada ou estimada sem fonte declarada.
- "Reforçar atenção" ou "ter mais cuidado" como action item.

## Referências

- [Google SRE Book: postmortem culture](https://sre.google/sre-book/postmortem-culture/)
- [Google SRE Book: postmortem example](https://sre.google/sre-book/example-postmortem/)
- [Google SRE Workbook: postmortem culture](https://sre.google/workbook/postmortem-culture/)
