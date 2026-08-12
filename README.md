# Desktop Monitoring App

Windows-first Python collector that reports host and network adapter telemetry, including mandatory MAC-address fields.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Run

```bash
desktop-monitoring
# or
python -m desktop_monitoring
```

Each run collects one snapshot and publishes it via `Publisher` (stdout today). When you add the API, switch to `HttpPublisher` so the same JSON is POSTed to the server. Previous snapshots are not deleted by the client.

## MAC addresses

### Where MAC addresses come from

On Windows, adapter MAC data is collected from PowerShell/`Get-NetAdapter` (current and permanent addresses), enriched with `Get-NetIPConfiguration` and `Get-NetRoute` for addressing and preferred-route detection. `psutil.net_if_addrs()` may be used as a supplemental source. Values are normalized to `AA:BB:CC:DD:EE:FF` before comparison or JSON output. Missing or invalid values become JSON `null` and are never fabricated.

### Why a Wi-Fi MAC address might be randomized

Modern operating systems often enable Wi-Fi MAC randomization for privacy. Randomized addresses typically set the IEEE locally administered bit. The collector exposes `is_randomized_or_locally_administered` and returns both `current_mac_address` and `permanent_mac_address` when they differ.

### Why MAC addresses can change

MACs can change because of OS privacy features, adapter replacement, driver reinstalls, OS upgrades, or enabling/disabling randomization. Treat them as network interface attributes, not immutable hardware serial numbers.

### Why a MAC address must not be used as the only computer identifier

Because MACs are mutable and sometimes randomized, `host_id` is composed from durable non-MAC anchors (hostname and machine GUID). `network.primary_mac_address` is reported separately for inventory/correlation and must not be the sole identity key.

### How the primary MAC address is selected

1. Prefer the MAC of the preferred/default-route adapter when it is a physical Ethernet/Wi-Fi adapter.
2. Include active adapters' MACs in `active_adapters` / `all_adapters`.
3. Exclude loopback from `physical_adapter_count`.
4. Do not select virtual/Docker/WSL/Hyper-V/VMware/VirtualBox/VPN/Bluetooth/disconnected adapters as primary unless that adapter owns the active preferred route and no physical alternative is available.
5. If current and permanent MACs differ, both are returned; primary uses the current MAC of the selected adapter when available.

## Tests

```bash
pytest -v
```
