import json

from system_info.printers import (
    Printer,
    _loads_ps_json,
    _page_count_from_properties,
    _windows_print_counts,
    _windows_printer_ports,
    classify_connection,
    collect_printers,
    extract_printer_ip,
)


def test_classify_connection_usb001():
    assert classify_connection("USB001") == "usb"


def test_classify_connection_ip_prefix():
    assert classify_connection("IP_192.168.1.50") == "network"


def test_classify_connection_bare_ipv4():
    assert classify_connection("192.168.1.50") == "network"


def test_classify_connection_ipv4_with_port():
    assert classify_connection("192.168.1.50:9100") == "network"


def test_classify_connection_custom_port_uses_resolved_address():
    assert classify_connection("LOBBY-PRINTER") == "other"
    assert classify_connection("LOBBY-PRINTER", "192.168.1.50") == "network"


def test_classify_connection_wsd():
    assert classify_connection("WSD-abc") == "network"
    assert classify_connection("WSD-1234.device") == "network"


def test_classify_connection_ipp():
    assert classify_connection("ipp://printer.local/ipp/print") == "network"
    assert classify_connection("ipps://printer.local/ipp/print") == "network"


def test_classify_connection_smb_unc():
    assert classify_connection("\\\\PRINTSERVER\\OfficePrinter") == "network"
    assert classify_connection("//PRINTSERVER/OfficePrinter") == "network"


def test_classify_connection_hostname():
    assert classify_connection("printer.office.local") == "network"
    assert classify_connection("printer.local:9100") == "network"


def test_classify_connection_virtual_and_local_not_network():
    assert classify_connection("PORTPROMPT:") == "other"  # Microsoft Print to PDF
    assert classify_connection("FILE:") == "other"
    assert classify_connection("LPT1:") == "other"
    assert classify_connection("COM1:") == "other"
    assert classify_connection("NUL:") == "other"
    assert classify_connection("Fax") == "other"


def test_classify_connection_invalid_ipv4_not_network():
    assert classify_connection("999.999.999.999") == "other"
    assert extract_printer_ip("999.999.999.999", "network") is None


def test_extract_printer_ip_valid_forms():
    assert extract_printer_ip("IP_192.168.1.50", "network") == "192.168.1.50"
    assert extract_printer_ip("192.168.1.50:9100", "network") == "192.168.1.50"
    assert extract_printer_ip("ipp://192.168.1.20/ipp/print", "network") == "192.168.1.20"
    assert extract_printer_ip("usb://HP/DeskJet", "usb") is None
    assert extract_printer_ip("socket://printer.local:9100", "network") is None


def test_printer_to_dict_includes_connection():
    payload = Printer(
        name="HP USB",
        port="USB001",
        connection="usb",
        ip=None,
        print_count=None,
    ).to_dict()
    assert payload["connection"] == "usb"
    assert payload["name"] == "HP USB"
    assert payload["port"] == "USB001"
    assert "print_count" in payload


def test_loads_ps_json_empty_and_malformed():
    assert _loads_ps_json("") == []
    assert _loads_ps_json("   ") == []
    assert _loads_ps_json("null") == []
    assert _loads_ps_json("not-json") == []
    assert _loads_ps_json("[]") == []


def test_loads_ps_json_one_object_versus_array():
    one = _loads_ps_json('{"Name": "USB001", "PrinterHostAddress": "10.0.0.1"}')
    assert len(one) == 1
    assert one[0]["Name"] == "USB001"
    many = _loads_ps_json(
        '[{"Name": "a"}, {"Name": "b"}, "skip"]'
    )
    assert [row["Name"] for row in many] == ["a", "b"]


def test_page_count_ignores_job_ids_and_loose_count_names():
    assert (
        _page_count_from_properties(
            [
                {"PropertyName": "JobCount", "Value": "3"},
                {"PropertyName": "NumberOfJobs", "Value": "4"},
                {"PropertyName": "JobId", "Value": "17"},
                {"PropertyName": "TotalCount", "Value": "99"},
            ]
        )
        is None
    )
    assert (
        _page_count_from_properties(
            [
                {"PropertyName": "JobCount", "Value": "3"},
                {"PropertyName": "PageCount", "Value": "128"},
            ]
        )
        == 128
    )
    assert _page_count_from_properties([]) is None
    assert _page_count_from_properties(None) is None


def test_windows_print_counts_missing_properties(monkeypatch):
    monkeypatch.setattr(
        "system_info.printers._run_powershell",
        lambda script, timeout=20.0: json.dumps(
            [{"Name": "HP USB", "Properties": [{"PropertyName": "JobCount", "Value": "2"}]}]
        ),
    )
    assert _windows_print_counts() == {}


def test_windows_printer_ports_empty_output(monkeypatch):
    monkeypatch.setattr("system_info.printers._run_powershell", lambda *a, **k: "")
    assert _windows_printer_ports() == {}
    monkeypatch.setattr("system_info.printers._run_powershell", lambda *a, **k: "{")
    assert _windows_printer_ports() == {}


def test_collect_printers_windows_full_matrix(monkeypatch):
    from system_info import printers

    monkeypatch.setattr(printers.os, "name", "nt")
    printers_payload = json.dumps(
        [
            {"Name": "HP USB", "PortName": "USB001"},
            {"Name": "Std TCP", "PortName": "IP_192.168.1.50"},
            {"Name": "Bare IP", "PortName": "192.168.1.50"},
            {"Name": "JetDirect", "PortName": "192.168.1.50:9100"},
            {"Name": "Lobby", "PortName": "LOBBY-PRINTER"},
            {"Name": "WSD Printer", "PortName": "WSD-abc"},
            {"Name": "IPP Printer", "PortName": "ipp://printer.local/ipp/print"},
            {"Name": "Office Share", "PortName": "\\\\PRINTSERVER\\OfficePrinter"},
            {"Name": "Microsoft Print to PDF", "PortName": "PORTPROMPT:"},
            {"Name": "File Printer", "PortName": "FILE:"},
            {"Name": "Dot Matrix", "PortName": "LPT1:"},
        ]
    )
    ports_payload = json.dumps(
        [
            {
                "Name": "LOBBY-PRINTER",
                "PrinterHostAddress": "192.168.1.50",
                "DeviceURL": "",
            },
            {
                "Name": "WSD-abc",
                "PrinterHostAddress": "",
                "DeviceURL": "http://192.168.1.77/wsd",
            },
        ]
    )

    def fake_run(cmd, timeout=8.0):
        script = cmd[4] if len(cmd) > 4 else ""
        if "Get-PrinterPort" in script:
            return ports_payload
        if "Get-PrinterProperty" in script:
            return "[]"
        if "Get-Printer" in script:
            return printers_payload
        return ""

    monkeypatch.setattr(printers, "_run", fake_run)
    info = collect_printers()
    usb_names = [p.name for p in info.usb]
    net = {p.name: p for p in info.network}
    other_names = [p.name for p in info.other]
    assert usb_names == ["HP USB"]
    assert net["Std TCP"].ip == "192.168.1.50"
    assert net["Bare IP"].ip == "192.168.1.50"
    assert net["JetDirect"].ip == "192.168.1.50"
    assert net["Lobby"].ip == "192.168.1.50"
    assert net["Lobby"].connection == "network"
    assert net["WSD Printer"].ip == "192.168.1.77"
    assert "IPP Printer" in net
    assert "Office Share" in net
    assert "Microsoft Print to PDF" in other_names
    assert "File Printer" in other_names
    assert "Dot Matrix" in other_names
    payload = info.to_dict()
    assert payload["usb"][0]["connection"] == "usb"
    assert all(p.print_count is None for p in info.usb + info.network + info.other)
