# Printers on reports (USB / Network / Other)

## Goal

Collect connected printers on each PC, classify as USB / Network / Other, store on reports, show count + full lists on the admin detail pane.

## Approach

OS CLI / stdlib only (no new deps):
- macOS: CUPS `lpstat -p` / `lpstat -v`
- Windows: PowerShell `Get-Printer`

## Payload

```json
{
  "printers": {
    "count": 3,
    "usb": [{"name": "HP DeskJet", "port": "usb://HP/..."}],
    "network": [{"name": "Office Laser", "port": "ipp://192.168.1.20/ipp"}],
    "other": [{"name": "Fax", "port": "Fax:"}]
  }
}
```

## Classification

- **USB:** URI/port contains `usb`
- **Network:** `ipp`, `ipps`, `socket`, `http`, `https`, `smb`, `lpd`, `wsd`, `tcp`, or `ip_` prefix
- **Other:** everything else

## Surfaces

- Desktop CLI: include in default full run + `--printers`
- API: optional `printers` on `Report`
- Dashboard: Printers section on selected PC detail
