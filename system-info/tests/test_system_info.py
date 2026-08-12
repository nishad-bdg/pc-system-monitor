import pytest

from system_info.geo import Location, geo_locate
from system_info.ip import get_private_ip, get_public_ip
from system_info.os_info import OSInfo, collect_os_info


class FakeResponse:
    def __init__(self, text="", payload=None):
        self._text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    @property
    def text(self):
        return self._text


def test_geo_locate_happy_path(monkeypatch):
    payload = {
        "status": "success",
        "query": "8.8.8.8",
        "city": "Mountain View",
        "regionName": "California",
        "country": "United States",
        "countryCode": "US",
        "lat": 37.4056,
        "lon": -122.0775,
        "isp": "Google LLC",
        "timezone": "America/Los_Angeles",
    }
    monkeypatch.setattr("system_info.geo.requests.get", lambda *a, **k: FakeResponse(payload=payload))
    loc = geo_locate("8.8.8.8")
    assert isinstance(loc, Location)
    assert loc.city == "Mountain View"
    assert loc.isp == "Google LLC"
    assert loc.lat == 37.4056


def test_geo_locate_failure_returns_none(monkeypatch):
    monkeypatch.setattr("system_info.geo.requests.get", lambda *a, **k: FakeResponse(payload={"status": "fail"}))
    assert geo_locate("8.8.8.8") is None


def test_geo_locate_request_exception_returns_none(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr("system_info.geo.requests.get", boom)
    assert geo_locate("8.8.8.8") is None


def test_get_public_ip(monkeypatch):
    monkeypatch.setattr("system_info.ip.requests.get", lambda *a, **k: FakeResponse(text="1.2.3.4"))
    assert get_public_ip() == "1.2.3.4"


def test_get_public_ip_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr("system_info.ip.requests.get", boom)
    assert get_public_ip() is None


def test_get_private_ip(monkeypatch):
    ip = get_private_ip()
    assert isinstance(ip, str) and ip


def test_collect_os_info_fields():
    info = collect_os_info()
    assert isinstance(info, OSInfo)
    assert info.system in ("Darwin", "Windows", "Linux")
    for field in ("system", "release", "machine", "processor", "python_version", "hostname"):
        assert getattr(info, field)


def test_location_to_dict():
    loc = Location(ip="1.2.3.4", city="Paris", region=None, country="France",
                   country_code="FR", lat=48.85, lon=2.35, isp="X", timezone="Europe/Paris")
    d = loc.to_dict()
    assert d["city"] == "Paris"
    assert set(d) == {"ip", "city", "region", "country", "country_code", "lat", "lon", "isp", "timezone"}
