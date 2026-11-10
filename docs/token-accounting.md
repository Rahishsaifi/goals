# Token accounting

Every mock model operation can write a `usage_events` row with an idempotency key.

- Unavailable telemetry stays `null` token fields with `usage_available=false`.
- Zero is distinct from unavailable.
- Estimated cost uses Decimal arithmetic and versioned rates when configured.
- Current POC rates for the mock provider are zero.
- Estimates are never labeled as an Azure invoice.
