---
id: cloud-s3-throttling
title: Throttling de object storage em picos de acesso
severity: high
services: [cloud, storage]
slo_impact: latency
last_reviewed: 2026-09-15
owner: platform
---

# Throttling de object storage em picos de acesso

Objetos com prefixo quente recebem `503 SlowDown` apesar de o serviço estar
saudável. O limite é por prefixo, não por bucket: a mitigação certa costuma ser
distribuir chaves, não aumentar clientes.

## Sintomas

- Aplicação retorna `503 SlowDown` ou `TooManyRequests` intermitente.
- Latência p99 de upload sobe em degrau, com throughput estável ou caindo.
- Erros concentrados em um prefixo (por exemplo, um diretório de data) e não em todo o bucket.
- Retries do SDK multiplicam o número de requisições e pioram o quadro.

## Impacto no SLO

O `latency` do caminho de dados degrada e, se o cliente não tiver retry correto,
boa parte vira `error-rate`. Jobs de processamento em lote atrasam em cascata,
consumindo `freshness` de relatórios que dependem desses objetos.

## Detecção

**Alerta:** `ObjectStorageSlowDown`

```promql
sum(rate(objectstore_requests_total{status="503", code="SlowDown"}[5m]))
  / sum(rate(objectstore_requests_total[5m])) > 0.01
```

**Alerta:** `UploadP99LatencyHigh`

```promql
histogram_quantile(0.99, sum by (le) (rate(objectstore_upload_seconds_bucket[5m]))) > 1.5
```

## Diagnóstico

1. Confirme que o erro é throttling e não permissão — são códigos diferentes.

   ```bash
   aws s3api put-object --bucket lab-data-lake --key probe/health.json --body /tmp/probe.json 2>&1 | head -5
   ```

   `SlowDown` confirma throttling; `AccessDenied` é outro caminho. Tempo: ~10 s.

2. Descubra a concentração por prefixo (é o eixo do limite).

   ```bash
   aws s3api list-objects-v2 --bucket lab-data-lake --prefix events/2026/09/15/ --max-keys 5 --output json
   ```

   Tempo: ~15 s.

3. Meça a taxa de requisições por prefixo para achar o ponto quente.

   ```bash
   aws cloudwatch get-metric-statistics --namespace AWS/S3 --metric-name AllRequests \
     --dimensions Name=BucketName,Value=lab-data-lake Name=FilterId,Value=entire-bucket \
     --start-time 2026-09-15T00:00:00Z --end-time 2026-09-15T01:00:00Z --period 60 --statistics Sum
   ```

   Tempo: ~20 s.

4. Verifique se o cliente está usando retry com backoff exponencial e jitter — retry agressivo amplifica o problema.

   ```bash
   grep -R "max_attempts\|retry_mode" "$HOME/.aws/config" || echo "no retry configuration found in aws config"
   ```

   Tempo: ~5 s.

5. Cheque se há muitos clientes lendo o mesmo objeto pequeno (hot key).

   ```bash
   aws s3api head-object --bucket lab-data-lake --key config/feature-flags.json
   ```

   Tempo: ~10 s.

6. Confirme se o erro acontece na borda de outra camada (proxy/CDN) e não no storage.

   ```bash
   curl -sS -o /dev/null -w 'http_code=%{http_code} time_total=%{time_total}\n' https://lab-data-lake.s3.amazonaws.com/probe/health.json
   ```

   Tempo: ~10 s.

## Mitigação

**Risco:** reescrever o particionamento de chaves exige mudança no produtor; mudar
o cliente para paralelizar mais só ajuda se o limite estiver concentrado, do
contrário aumenta a pressão.

1. Reduza a taxa de requisições atrasando o produtor em vez de insistir.

   ```bash
   sleep 30 && aws s3 cp /var/spool/exports/2026-09-15.ndjson s3://lab-data-lake/exports/2026/09/15/part-0001.ndjson
   ```

2. Distribua o prefixo incluindo um hash estável da chave (mitigação estrutural).

   ```bash
   key="events/2026/09/15/shard-$(printf '%s' "$ITEM_ID" | shasum -a 256 | cut -c1-4)/item.json"
   aws s3 cp "$LOCAL_FILE" "s3://lab-data-lake/$key"
   ```

3. Ligue cache local para objetos pequenos lidos por muitos consumidores ao mesmo tempo.

   ```bash
   export FEATURE_FLAG_TTL_SECONDS=300
   ```

4. Se o gargalo for o lote noturno inteiro, escale horizontalmente com `--max-concurrent-requests` controlado.

   ```bash
   aws configure set default.s3.max_concurrent_requests 4
   aws s3 sync /var/spool/exports s3://lab-data-lake/exports/2026/09/15/ --exclude '*.tmp'
   ```

## Escalonamento

- Acione o time de plantão do serviço quando o produtor do lote estiver no caminho crítico e o atraso afetar dados de negócio.
- Acione o time de plantão de plataforma se o padrão de chaves exigir mudança de esquema de armazenamento.
- Abra caso no provedor apenas depois de confirmar que a taxa por prefixo está abaixo dos limites documentados: throttling agregado pode ser limite de conta.

## Verificação

1. A taxa de `503 SlowDown` volta a zero por 15 minutos consecutivos.

   ```bash
   aws cloudwatch get-metric-statistics --namespace AWS/S3 --metric-name 5xxErrors \
     --dimensions Name=BucketName,Value=lab-data-lake Name=FilterId,Value=entire-bucket \
     --start-time 2026-09-15T01:00:00Z --end-time 2026-09-15T02:00:00Z --period 300 --statistics Sum
   ```

2. O lote de atraso terminou e a fila de pendências voltou ao normal.

   ```bash
   aws s3 ls s3://lab-data-lake/exports/2026/09/15/ | tail -5
   ```

3. p99 de upload volta ao patamar anterior em um ciclo completo de carga.

## Prevenção

- Use prefixos com hash para dados gerados em massa; nunca serialize por timestamp puro.
- Configure retry com backoff exponencial e jitter, com teto de tentativas.
- Cache objetos de configuração pequenos no cliente em vez de reler a cada requisição.
- Alerte sobre taxa de 503 por prefixo, não só por bucket — o bucket esconde o ponto quente.

## Referências

- [AWS: best practices design patterns for Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [AWS: partitioning and performance guidelines](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html)
- [AWS CLI: S3 configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
- [AWS: request rate and performance considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/request-rate-perf-considerations.html)
