from dataclasses import dataclass

import requests

GEO_URL = "http://ip-api.com/json/"
GEO_TIMEOUT = 5


@dataclass
class Location:
    ip: str
    city: str | None
    region: str | None
    country: str | None
    country_code: str | None
    lat: float | None
    lon: float | None
    isp: str | None
    timezone: str | None

    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "city": self.city,
            "region": self.region,
            "country": self.country,
            "country_code": self.country_code,
            "lat": self.lat,
            "lon": self.lon,
            "isp": self.isp,
            "timezone": self.timezone,
        }


def geo_locate(ip: str) -> Location | None:
    """Resolve an IP to a Location via ip-api.com. Returns None on failure."""
    try:
        resp = requests.get(f"{GEO_URL}{ip}", timeout=GEO_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, OSError):
        return None

    if data.get("status") != "success":
        return None

    return Location(
        ip=data.get("query", ip),
        city=data.get("city"),
        region=data.get("regionName"),
        country=data.get("country"),
        country_code=data.get("countryCode"),
        lat=data.get("lat"),
        lon=data.get("lon"),
        isp=data.get("isp"),
        timezone=data.get("timezone"),
    )
