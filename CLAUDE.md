The previous prompt mentioned an adapter MAC address, but this update makes MAC-address collection explicit for all physical and active adapters. Add the following section to the Claude prompt:

## Mandatory MAC-address collection

The application must collect the MAC addresses of the computer’s network adapters.

For every network adapter, collect:

* Adapter name
* Adapter description
* Interface index
* Interface GUID, when available
* Permanent/physical MAC address
* Current MAC address
* Normalized MAC address
* Adapter type
* Physical or virtual status
* Active or inactive status
* Connected or disconnected status
* Preferred/default-route status

Use this normalized MAC-address format:

```text
AA:BB:CC:DD:EE:FF
```

Return `null` when a MAC address is genuinely unavailable. Do not generate or fabricate one.

### MAC-address rules

* Collect MAC addresses for all physical Ethernet and Wi-Fi adapters.
* Include the MAC address of the currently active adapter.
* Identify the MAC address belonging to the preferred/default-route adapter.
* Exclude loopback interfaces from physical-adapter totals.
* Do not use a virtual, Docker, WSL, Hyper-V, VMware, VirtualBox, VPN, Bluetooth, or disconnected adapter as the primary MAC address unless it owns the active preferred route and no physical alternative is available.
* Keep virtual-adapter details available in the per-interface list.
* Detect locally administered or randomized MAC addresses when possible.
* Add an `is_randomized_or_locally_administered` boolean field.
* Do not treat the MAC address as a guaranteed permanent device identifier because Wi-Fi MAC randomization and adapter replacement can change it.
* Do not use only the MAC address as the application’s `host_id`.
* If the permanent hardware MAC and current MAC differ, return both without guessing which should identify the computer.
* Normalize MAC addresses consistently before comparison or JSON serialization.
* Never collect Wi-Fi passwords or security keys.

Use reliable Windows information sources such as:

* `Get-NetAdapter`
* `Get-NetIPConfiguration`
* `Get-NetRoute`
* CIM
* WMI
* `psutil.net_if_addrs()`

PowerShell commands must use a timeout, must not use `shell=True`, and must return structured JSON for safe parsing.

## Updated network JSON structure

Use a network structure similar to:

```json
{
  "network": {
    "connection_type": "wifi",
    "local_ipv4": "192.168.1.25",
    "primary_mac_address": "AA:BB:CC:DD:EE:FF",
    "preferred_adapter": {
      "name": "Wi-Fi",
      "description": "Intel(R) Wi-Fi 6 AX201 160MHz",
      "interface_index": 12,
      "interface_guid": null,
      "adapter_type": "wifi",
      "is_physical": true,
      "is_virtual": false,
      "is_active": true,
      "is_connected": true,
      "is_preferred": true,
      "current_mac_address": "AA:BB:CC:DD:EE:FF",
      "permanent_mac_address": "AA:BB:CC:DD:EE:FF",
      "is_randomized_or_locally_administered": false,
      "ipv4_addresses": ["192.168.1.25"],
      "ipv6_addresses": [],
      "subnet_mask": "255.255.255.0",
      "default_gateway": "192.168.1.1",
      "dns_servers": ["192.168.1.1"],
      "ssid": "Office-WiFi",
      "link_speed_mbps": 866
    },
    "physical_adapter_count": 1,
    "active_adapter_count": 1,
    "active_adapters": [],
    "all_adapters": [],
    "bandwidth": {
      "since_previous_collection": {},
      "since_system_boot": {},
      "application_observed_cumulative": {},
      "per_interface": []
    }
  }
}
```

The `active_adapters` and `all_adapters` arrays must include MAC-address fields for each adapter.

## Updated network tests

Add unit tests for:

* MAC-address normalization
* Missing MAC addresses
* Invalid MAC-address values
* Wi-Fi and Ethernet MAC selection
* Preferred-adapter MAC selection
* Physical versus virtual adapter classification
* Locally administered MAC detection
* Randomized Wi-Fi MAC handling
* Different current and permanent MAC addresses
* Exclusion of loopback adapters
* Prevention of virtual-adapter MAC selection when a physical preferred adapter exists

Also update the README to explain:

* Where MAC addresses come from
* Why a Wi-Fi MAC address might be randomized
* Why MAC addresses can change
* Why a MAC address must not be used as the only computer identifier
* How the primary MAC address is selected

Before finalizing the project, verify that the generated JSON always includes:

* `network.primary_mac_address`
* `network.preferred_adapter.current_mac_address`
* `network.preferred_adapter.permanent_mac_address`
* MAC-address fields for every item in `active_adapters`
* MAC-address fields for every item in `all_adapters`
