---
id: net-tls-cert-expiry
title: Certificado TLS próximo do vencimento ou expirado
severity: critical
services: [network, edge]
slo_impact: availability
last_reviewed: 2026-09-15
owner: platform
---

# Certificado TLS próximo do vencimento ou expirado

Certificado expirado é uma indisponibilidade total e autoprovocada. A diferença
entre um incidente de 5 minutos e um de 3 horas é detectar antes do relógio
passar do `notAfter`.

## Sintomas

- Clientes recebem erro de handshake (`certificate has expired`, `unable to verify the first certificate`).
- Navegador ou SDK rejeita a conexão mesmo com o backend saudável.
- Alertas de disponibilidade da borda disparam sem mudança de código.
- Health check externo começa a falhar antes do usuário perceber.

## Impacto no SLO

`availability` pode ir a zero se o certificado estiver na borda: nenhuma
requisição completa o handshake. Mesmo com fallback, o `error-rate` sobe nos
clientes que validam cadeia e nome.

## Detecção

**Alerta:** `TLSCertificateExpiringSoon`

```promql
tls_certificate_expiry_seconds < 30 * 24 * 3600
```

**Alerta:** `TLSCertificateNotAfterSoon` (a menos de 7 dias)

```promql
tls_certificate_expiry_seconds < 7 * 24 * 3600
```

## Diagnóstico

1. Leia a data real de expiração e o emissor direto do endpoint.

   ```bash
   openssl s_client -connect example.org:443 -servername example.org -brief </dev/null
   ```

   Tempo: ~10 s.

2. Verifique a cadeia completa, incluindo intermediários.

   ```bash
   openssl s_client -connect example.org:443 -servername example.org -showcerts </dev/null | grep -E 's:|i:'
   ```

   Tempo: ~10 s.

3. Confirme que o nome verificado está no SAN (não basta ter um certificado válido).

   ```bash
   openssl s_client -connect example.org:443 -servername example.org </dev/null 2>/dev/null | openssl x509 -noout -text | sed -n '/Subject Alternative Name/,+3p'
   ```

   Tempo: ~10 s.

4. Descubra onde o certificado está montado (secret, arquivo ou provedor) para saber quem deve renovar.

   ```bash
   kubectl -n prod get ingress -o custom-columns=NAME:.metadata.name,TLS:.spec.tls[*].secretName,HOST:.spec.rules[*].host
   kubectl -n prod get certificate -o custom-columns=NAME:.metadata.name,READY:.status.conditions[*].status,RENEWAL:.status.renewalTime 2>/dev/null || echo "no cert-manager Certificate objects in prod"
   ```

   Tempo: ~15 s.

5. Confirme se a renovação automática falhou e por qual motivo.

   ```bash
   kubectl -n prod describe certificate checkout-api-tls | sed -n '/Events/,$p'
   ```

   Tempo: ~15 s.

6. Verifique exposição relevante: quantos hosts e serviços compartilham o mesmo certificado.

   ```bash
   kubectl -n prod get ingress -A -o jsonpath='{range .items[*]}{.spec.tls[*].hosts}{"\n"}{end}' | sort -u
   ```

   Tempo: ~15 s.

## Mitigação

**Risco:** substituir o secret sem reiniciar o controlador de entrada não recarrega
o certificado; forçar reload pode derrubar conexões ativas por alguns segundos.

1. Renove pelo caminho automatizado quando ele existir e force a ordem pendente.

   ```bash
   kubectl -n prod annotate certificate checkout-api-tls cert-manager.io/issue-temporary-certificate="true" --overwrite
   kubectl -n prod describe certificate checkout-api-tls | grep -A3 'Status'
   ```

2. Emita um certificado manualmente quando a automação estiver bloqueada e a expiração for iminente.

   ```bash
   openssl req -new -key tls.key -out tls.csr -subj "/CN=example.org"
   openssl x509 -req -in tls.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -days 90 -out tls.crt
   ```

3. Atualize o secret com a cadeia completa (folha + intermediário, nesta ordem).

   ```bash
   kubectl -n prod create secret tls checkout-api-tls --cert=tls.crt --key=tls.key --dry-run=client -o yaml | kubectl apply -f -
   ```

4. Recarregue o controlador de entrada para ler o novo secret.

   ```bash
   kubectl -n ingress-nginx rollout restart deploy ingress-nginx-controller
   kubectl -n ingress-nginx rollout status deploy ingress-nginx-controller --timeout=120s
   ```

5. Reduza risco de nova expiração silenciosa emitindo por 90 dias e agendando a correção da automação.

   ```bash
   openssl x509 -in tls.crt -noout -dates -issuer -subject
   ```

## Escalonamento

- Acione o time de plantão de plataforma imediatamente quando o certificado já expirou (indisponibilidade total da borda).
- Acione o time de plantão do serviço quando o certificado for específico do serviço e a renovação depender do dono.
- Suba para o time de segurança quando a emissão manual exigir exceção de política de chave privada.

## Verificação

1. O endpoint apresenta certificado válido, com data futura confortável e SAN correto.

   ```bash
   openssl s_client -connect example.org:443 -servername example.org -verify_return_error </dev/null 2>&1 | grep -E 'Verify return code|notAfter'
   ```

2. O health check externo volta a responder `200` e o handshake completa em todos os hosts do mesmo certificado.

   ```bash
   curl -sS -o /dev/null -w 'http_code=%{http_code} tls=%{ssl_verify_result}\n' https://example.org/
   ```

3. A automação de renovação está saudável e com próxima execução agendada.

## Prevenção

- Alerte em 30 dias **e** em 7 dias; um único alerta é fácil de postergar.
- Teste a renovação automatizada em laboratório antes de depender dela em produção.
- Monitore `renewalTime` e falhas de emissão, não apenas a data de expiração.
- Mantenha procedimento de emissão manual documentado e ensaiado para o dia em que a automação falhar.

## Referências

- [OpenSSL: s_client documentation](https://docs.openssl.org/3.0/man1/openssl-s_client/)
- [RFC 8446: TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 6797: HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797)
- [Kubernetes: ingress TLS](https://kubernetes.io/docs/concepts/services-networking/ingress/)
