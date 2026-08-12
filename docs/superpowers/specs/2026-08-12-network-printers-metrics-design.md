# Network bandwidth + printer IP / print count

## Network

Report field `network`:
- `bytes_sent` / `bytes_recv` — totals since boot
- `send_rate_bps` / `recv_rate_bps` — short sample rates

## Printers

Each printer:
- `ip` — IPv4 extracted from network port/URI (else null)
- `print_count` — best-effort when OS/printer exposes it (else null)
