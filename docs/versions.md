# Versões de referência

As versões dos componentes citados nos runbooks (kubectl, AWS CLI v2) são
verificadas na origem upstream pelo `maintenance.yml` toda semana. O bloco
abaixo é gerado por `tools/update_versions.py`; o workflow só commita quando há
diferença real.

<!-- BEGIN GENERATED VERSIONS -->
| Componente | Versão estável | Verificado em (UTC) | Fonte |
| --- | --- | --- | --- |
| Kubernetes | `1.37.0` | 2026-09-16 | https://dl.k8s.io/release/stable.txt |
| kubectl | `1.37.0` | 2026-09-16 | https://dl.k8s.io/release/stable.txt |
| AWS CLI v2 | `2.36.46` | 2026-09-16 | https://github.com/aws/aws-cli/releases |
<!-- END GENERATED VERSIONS -->

## Por que isso existe

Comando de runbook envelhece. Quando o `kubectl` muda a saída de `describe` ou a
AWS CLI v2 muda uma flag, o passo do runbook para de funcionar exatamente na hora
em que ninguém tem tempo de improvisar. Registrar a versão em que o runbook foi
validado transforma "funciona na minha máquina" em informação verificável.

## Política

- O workflow semanal consulta `https://dl.k8s.io/release/stable.txt` e os releases
  oficiais do `aws cli` no GitHub.
- Falha de rede não apaga o valor anterior: o script preserva a última versão conhecida e sai com código 1 para o workflow reportar.
- Mudança de versão maior gera revisão do runbook afetado, não apenas atualização da tabela.

## Ferramentas locais desta máquina

O repositório foi construído e verificado em macOS com:

```bash
python3 --version
```

```text
Python 3.9.6
```

Os checks de `kubectl` e `aws` degradam para `SKIPPED` quando a ferramenta não
está instalada — por isso `sretriage run` funciona igual em um laptop sem
ferramentas de nuvem e em um runner de CI limpo.
