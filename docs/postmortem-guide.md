# Guia de postmortem sem culpados

Postmortem existe para mudar o sistema, não para encontrar quem errou. Um
documento que termina em "fulano fez o deploy errado" não gerou nenhuma ação
capaz de impedir a repetição.

## O que entra

- **Impacto medido**: usuários afetados, SLOs violados, error budget consumido, com a fonte do número.
- **Linha do tempo com fonte**: cada evento com hora e origem (alerta, pipeline, comando, relato). Sem reconstrução de memória no lugar de fato.
- **Causas contribuintes**: múltiplas condições que juntas produziram o incidente.
- **Fatores latentes**: decisões antigas que aumentaram o impacto (falta de validação, painel sem dimensão de versão, acesso restrito).
- **O que funcionou bem**: reconhecer o que a resposta fez certo mantém a prática viva.
- **Action items verificáveis**: dono, prazo e critério de verificação.

## O que não entra

- Nome de pessoa como causa. Se uma pessoa específica é o fator decisivo, o sistema permitiu isso.
- Adjetivos moralizantes no lugar de análise.
- Métrica estimada apresentada como medida.
- "Ter mais atenção", "reforçar cuidado", "melhorar a comunicação" como action item.
- Narrativa defensiva ou justificativa do time.

## Exemplos

### Ruim: culpa no lugar de causa

> O deploy foi feito com uma variável de ambiente errada. O time precisa prestar
> mais atenção nas configurações antes de subir para produção.

Problemas: nomeia comportamento, sem causa sistêmica, sem ação verificável, culpa
disfarçada de recomendação.

### Bom: causa sistêmica + ação verificável

> A instância nova subiu sem a variável `PAYMENT_PROVIDER_URL`, obrigatória desde
> 2025. O manifesto veio de um template que não é atualizado desde a migração de
> provedor, e a pipeline não valida chaves obrigatórias: qualquer serviço que use
> esse template sobe com a mesma falha. Ação 1: validação de schema de
> configuração na pipeline (dono: developer-experience, prazo 2026-09-30,
> verificação: pipeline vermelha com configuração incompleta). Ação 2: template
> único versionado no repositório de plataforma (dono: platform, prazo 2026-10-10,
> verificação: nenhum manifesto com chave ausente no cluster).

### Ruim: causa raiz "humana"

> Causa raiz: falha humana.

### Bom: gatilho, causas contribuintes e fatores latentes

> Gatilho: deploy da revisão 42. Causas contribuintes: (1) migração de banco
> aplicada em deploy único, sem compatibilidade para trás; (2) painel sem dimensão
> de revisão, impedindo correlação rápida; (3) rollback documentado apenas para
> código, sem procedimento de reconciliação de dados. Fatores latentes: falta de
> validação de configuração na pipeline e ausência de canário obrigatório.

## Action items

| Tipo | Exemplo | Critério de verificação |
| --- | --- | --- |
| Preventivo | validar configuração na pipeline | pipeline falha com config inválida |
| Detecção | adicionar alerta de ausência de progresso de negócio | alerta dispara em teste de falha injetada |
| Resposta | ensaiar rollback com migração aplicada | relatório de ensaio assinado |
| Documentação | publicar runbook de reconciliação | runbook passa no lint do CI |

Cada item precisa de dono nomeado e data. Item sem dono é intenção, não
compromisso. No follow-up, revisar itens vencidos na semana seguinte: o que
importa não é o documento, é o que mudou depois dele.

## Prazos de referência

- `crítica`: postmortem em até 5 dias úteis.
- `alta`: postmortem em até 10 dias úteis.
- `média`: opcional, recomendado em caso de recorrência.
- Follow-up dos action items: revisão semanal até o fechamento.

## Referências

- [Google SRE Book: postmortem culture](https://sre.google/sre-book/postmortem-culture/)
- [Google SRE Book: example postmortem](https://sre.google/sre-book/example-postmortem/)
- [Google SRE Workbook: postmortem culture](https://sre.google/workbook/postmortem-culture/)
