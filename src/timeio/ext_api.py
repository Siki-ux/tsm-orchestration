import requests
import json
import base64
import re

from abc import ABC, abstractmethod
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta

from timeio.feta import Thing
from timeio.typehints import MqttPayload
from timeio.crypto import decrypt, get_crypt_key


class NoHttpsError(Exception):
    pass


class ExtApiRequestError(Exception):
    def __init__(self, msg, status_code=None):
        self.msg = f"{msg}. Status code: {status_code}" if status_code else msg
        super().__init__(self.msg)


class ExtApiSyncer(ABC):
    @abstractmethod
    def fetch_api_data(self, thing: Thing, content: MqttPayload.SyncExtApiT):
        raise NotImplementedError

    @abstractmethod
    def do_parse(self, api_response) -> dict:
        raise NotImplementedError


def request_with_handling(method, url, timeout=(10, 60), **kwargs):
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        if status_code == 401:
            raise ExtApiRequestError(
                f"Unauthorized for url {url}", status_code=status_code
            )
        elif status_code == 403:
            raise ExtApiRequestError("Forbidden", status_code=status_code)
        else:
            raise ExtApiRequestError("HTTP request failed", status_code)
    except requests.exceptions.RequestException as e:
        raise ExtApiRequestError(f"Network error: {e}")


RESULT_TYPE_MAPPING = {
    0: "result_number",
    1: "result_string",
    2: "result_json",
    3: "result_boolean",
}


class BoschApiSyncer(ExtApiSyncer):

    def fetch_api_data(self, thing: Thing, content: MqttPayload.SyncExtApiT):
        settings = thing.ext_api.settings
        server_url = (
            f"{settings['endpoint']}/{settings['sensor_id']}/"
            f"{content['datetime_from']}/{content['datetime_to']}"
        )
        if urlparse(server_url).scheme != "https":
            raise NoHttpsError(f"{server_url} is not https")
        password = decrypt(settings["password"], get_crypt_key())
        headers = {
            "Authorization": f"{self.basic_auth(settings['username'], password)}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        response = request_with_handling("GET", server_url, headers=headers)

        return response.json()

    def do_parse(self, api_response):
        bodies = []
        for entry in api_response:
            obs = entry["payload"]
            source = {
                "sensor_id": obs.pop("deviceID") if "deviceID" in obs else "not found",
                "observation_type": obs.pop("Type"),
            }
            if "LocalTime" in obs:
                obs.pop("LocalTime", None)  # Remove LocalTime if present
            if "IMEI" in obs:
                obs["IMEI"] = int(obs["IMEI"])  # Convert IMEI to int if present
            timestamp = obs.pop("UTC")
            for parameter, value in obs.items():
                if value:
                    body = {
                        "result_time": timestamp,
                        "result_type": 0,
                        "datastream_pos": parameter,
                        "result_number": value,
                        "parameters": json.dumps(
                            {"origin": "bosch_data", "column_header": source}
                        ),
                    }
                    bodies.append(body)
        return {"observations": bodies}

    @staticmethod
    def basic_auth(username, password):
        credential = f"{username}:{password}"
        b_encoded_credential = base64.b64encode(credential.encode("ascii")).decode(
            "ascii"
        )
        return f"Basic {b_encoded_credential}"


class TsystemsApiSyncer(ExtApiSyncer):
    tsystems_base_url = (
        "https://moc.caritc.de/sensorstation-management/api/measurements/average"
    )
    tsytems_auth_url = (
        "https://moc.caritc.de/auth/realms/lcmm/protocol/openid-connect/token"
    )

    def fetch_api_data(self, thing: Thing, content: MqttPayload.SyncExtApiT):
        settings = thing.ext_api.settings
        pw_dec = decrypt(settings["password"], get_crypt_key())
        bearer_token = self.get_bearer_token(settings["username"], pw_dec)
        headers = {"Accept": "*/*", "Authorization": f"Bearer {bearer_token}"}
        params = {
            "aggregationTime": "FINEST",
            "aggregationValues": "ALL_FIELDS",
            "from": content["datetime_from"],
            "to": content["datetime_to"],
        }
        response = request_with_handling(
            "GET",
            f'{self.tsystems_base_url}/{settings["group"]}/{settings["station_id"]}',
            headers=headers,
            params=params,
        )
        return response.json()

    def do_parse(self, api_response):
        bodies = []
        for entry in api_response:
            source = {
                "sensor_id": entry.pop("deviceId"),
                "location_id": entry.pop("locationId"),
                "aggregation_time": "hourly",
            }
            timestamp = entry.pop("sendTimestamp")
            for parameter, value in entry.items():
                if value:
                    body = {
                        "result_time": self.unix_ts_to_str(timestamp),
                        "result_type": 0,
                        "result_number": value,
                        "datastream_pos": parameter,
                        "parameters": json.dumps(
                            {"origin": "tsystems_data", "column_header": source}
                        ),
                    }
                    bodies.append(body)
        return {"observations": bodies}

    @staticmethod
    def unix_ts_to_str(ts_unix: int) -> str:
        """Convert unix timestamp to datetime string"""
        dt = datetime.fromtimestamp(ts_unix, tz=timezone.utc)
        ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        return ts_str

    def get_bearer_token(self, username: str, password: str) -> str:
        """Get bearer token for API authentication"""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        payload = {
            "client_id": "lcmm",
            "grant_type": "password",
            "username": username,
            "password": password,
        }
        response = request_with_handling(
            "POST", self.tsytems_auth_url, headers=headers, data=payload
        )
        return response.json()["access_token"]


class UbaApiSyncer(ExtApiSyncer):
    uba_componsents_url = (
        "https://www.umweltbundesamt.de/api/air_data/v3/components/json"
    )
    uba_scopes_url = "https://www.umweltbundesamt.de/api/air_data/v3/scopes/json"
    uba_limits_url = "https://www.umweltbundesamt.de/api/air_data/v3/measures/limits"
    uba_measures_url = "https://www.umweltbundesamt.de/api/air_data/v3/measures/json"
    uba_airquality_url = (
        "https://www.umweltbundesamt.de/api/air_data/v3/airquality/json"
    )

    def fetch_api_data(self, thing: Thing, content: MqttPayload.SyncExtApiT):
        settings = thing.ext_api.settings
        station_id = settings["station_id"]
        date_from, time_from, date_to, time_to = self.parse_timeranges(
            content["datetime_from"], content["datetime_to"]
        )
        components, scopes = self.get_components_and_scopes()
        measure_data = self.combine_measure_responses(
            station_id, date_from, date_to, time_from, time_to, components, scopes
        )
        aqi_data = self.get_airquality_data(
            station_id, date_from, date_to, time_from, time_to, components
        )
        return {
            "measure_data": measure_data,
            "aqi_data": aqi_data,
            "station_id": station_id,
        }

    def do_parse(self, api_response):
        parsed_measure_data = self.parse_measure_data(
            api_response["measure_data"], api_response["station_id"]
        )
        parsed_aqi_data = self.parse_aqi_data(
            api_response["aqi_data"], api_response["station_id"]
        )
        return {"observations": parsed_measure_data + parsed_aqi_data}

    @staticmethod
    def parse_timeranges(dt_from_str, dt_to_str):
        dt_from = datetime.strptime(dt_from_str, "%Y-%m-%d %H:%M:%S")
        dt_to = datetime.strptime(dt_to_str, "%Y-%m-%d %H:%M:%S")
        date_from = dt_from.date().strftime("%Y-%m-%d")
        time_from = dt_from.hour
        date_to = dt_to.date().strftime("%Y-%m-%d")
        time_to = dt_to.hour
        return date_from, time_from, date_to, time_to

    @staticmethod
    def adjust_datetime(datetime_str: str) -> str:
        """UBA API returns datetime format with hours from 1 to 24 so it
        has to be parsed for timeIO DB API
        """
        date = datetime.strptime(datetime_str[0:10], "%Y-%m-%d")
        date_adjusted = date + timedelta(days=1)

        return date_adjusted.strftime("%Y-%m-%d %H:%M:%S")

    def get_components_and_scopes(self):
        """Get components (i.e measured quantites) and scopes
        (aggregation infos) for later mapping
        """
        response_components = request_with_handling("GET", self.uba_componsents_url)
        response_scopes = request_with_handling("GET", self.uba_scopes_url)
        components = {
            int(v[0]): v[1]
            for k, v in response_components.json().items()
            if k not in ["count", "indices"]
        }
        scopes = {
            int(v[0]): v[1]
            for k, v in response_scopes.json().items()
            if k not in ["count", "indices"]
        }
        return components, scopes

    def get_station_info(self, station_id: str) -> list:
        """Get all available components and scope combinations of a given
        station
        """
        station_info = list()
        response = request_with_handling("GET", self.uba_limits_url)
        response_json = response.json()["data"]
        for k, v in response_json.items():
            if v[2] == station_id:
                station_info.append({"scope": int(v[0]), "component": int(v[1])})
        return station_info

    def request_measure_endpoint(
        self,
        station_id: str,
        component_id: int,
        scope_id: int,
        date_from: str,
        date_to: str,
        time_from: int,
        time_to: int,
    ) -> dict:
        """Request uba api measure endpoint for a given component and scope
        and a given time range
        """
        params = {
            "date_from": date_from,
            "date_to": date_to,
            "time_from": time_from,
            "time_to": time_to,
            "station": station_id,
            "component": component_id,
            "scope": scope_id,
        }
        response = request_with_handling(
            "GET",
            self.uba_measures_url,
            params=params,
        )
        response_json = response.json()
        if response_json["data"]:
            return response_json["data"][station_id]
        else:
            return response_json["data"]

    def combine_measure_responses(
        self,
        station_id: str,
        date_from: str,
        date_to: str,
        time_from: int,
        time_to: int,
        components: dict,
        scopes: dict,
    ) -> list:
        """Combine uba respones for all component/scope combinations into
        one object
        """
        measure_data = list()
        station_info = self.get_station_info(station_id)
        for entry in station_info:
            response = self.request_measure_endpoint(
                station_id,
                entry["component"],
                entry["scope"],
                date_from,
                date_to,
                time_from,
                time_to,
            )
            for k, v in response.items():
                measure_data.append(
                    {
                        "timestamp": v[3],
                        "value": v[2],
                        "measure": f"{components[entry['component']]} {scopes[entry['scope']]}",
                    }
                )
        return measure_data

    def parse_measure_data(self, measure_data: list, station_id: str) -> list:
        """Creates POST body from combined uba measures data"""
        bodies = []
        source = {
            "uba_station_id": station_id,
            "endpoint": "/measures",
        }
        for entry in measure_data:
            if entry["timestamp"][11:13] == "24":
                entry["timestamp"] = self.adjust_datetime(entry["timestamp"])
            if entry["value"]:
                body = {
                    "result_time": entry["timestamp"],
                    "result_type": 0,
                    "result_number": entry["value"],
                    "datastream_pos": entry["measure"],
                    "parameters": json.dumps(
                        {"origin": "uba_data", "column_header": source}
                    ),
                }
                bodies.append(body)
        return bodies

    def get_airquality_data(
        self,
        station_id: str,
        date_from: str,
        date_to: str,
        time_from: int,
        time_to: int,
        components: dict,
    ) -> list:
        """Request uba api airquality endpoint for a given station_id and
        time range
        """
        params = {
            "date_from": date_from,
            "date_to": date_to,
            "time_from": time_from,
            "time_to": time_to,
            "station": station_id,
        }
        response = request_with_handling("GET", self.uba_airquality_url, params=params)
        response_json = response.json()
        if not response_json["data"]:
            return []

        response_data = response_json["data"][station_id]
        aqi_data = []
        for k, v in response_data.items():
            pollutant_info = list()
            for i in range(3, len(v)):
                entry = {"component": components[v[i][0]], "airquality_index": v[i][2]}
                pollutant_info.append(entry)
            aqi_data.append(
                {
                    "timestamp": v[0],
                    "airquality_index": v[1],
                    "data_complete": v[2],
                    "pollutant_info": pollutant_info,
                }
            )
        return aqi_data

    def parse_aqi_data(self, aqi_data: list, station_id: str) -> list:
        """Creates POST body from uba air quality data"""
        bodies = []
        for entry in aqi_data:
            source = {
                "uba_station_id": station_id,
                "endpoint": "/airquality",
                "pollutant_info": entry["pollutant_info"],
            }
            if entry["timestamp"][11:13] == "24":
                entry["timestamp"] = self.adjust_datetime(entry["timestamp"])
            if entry["airquality_index"]:
                body = {
                    "result_time": entry["timestamp"],
                    "result_type": 0,
                    "result_number": entry["airquality_index"],
                    "datastream_pos": "AQI",
                    "parameters": json.dumps(
                        {"origin": "uba_data", "column_header": source}
                    ),
                }
                bodies.append(body)
        return bodies


class DwdApiSyncer(ExtApiSyncer):
    PARAMETER_MAPPING = {
        "cloud_cover": 0,
        "condition": 1,
        "dew_point": 0,
        "icon": 1,
        "precipitation": 0,
        "precipitation_probability": 0,
        "precipitation_probability_6h": 0,
        "pressure_msl": 0,
        "relative_humidity": 0,
        "solar": 0,
        "sunshine": 0,
        "temperature": 0,
        "visibility": 0,
        "wind_direction": 0,
        "wind_speed": 0,
        "wind_gust_direction": 0,
        "wind_gust_speed": 0,
    }
    brightsky_base_url = "https://api.brightsky.dev/weather"

    def fetch_api_data(self, thing: Thing, content: MqttPayload.SyncExtApiT):
        settings = thing.ext_api.settings
        params = {
            "dwd_station_id": settings["station_id"],
            "date": content["datetime_from"],
            "last_date": content["datetime_to"],
            "units": "dwd",
        }
        response = request_with_handling("GET", self.brightsky_base_url, params=params)
        return response.json()

    def do_parse(self, api_response):
        observation_data = api_response["weather"]
        source = api_response["sources"][0]
        bodies = []
        for obs in observation_data:
            timestamp = obs.pop("timestamp")
            obs.pop("fallback_source_ids", None)
            obs.pop("source_id", None)
            for parameter, value in obs.items():
                if value:
                    result_type = self.PARAMETER_MAPPING[parameter]
                    body = {
                        "result_time": timestamp,
                        "result_type": result_type,
                        "datastream_pos": parameter,
                        RESULT_TYPE_MAPPING[result_type]: value,
                        "parameters": json.dumps(
                            {"origin": "dwd_data", "column_header": source}
                        ),
                    }
                    bodies.append(body)
        return {"observations": bodies}


class TtnApiSyncer(ExtApiSyncer):
    @staticmethod
    def dynamic_parameter_mapping(v):
        if isinstance(v, bool):
            return 3
        elif isinstance(v, (int, float)):
            return 0
        elif isinstance(v, str):
            return 1
        elif isinstance(v, dict):
            return 2
        else:
            raise ExtApiRequestError(
                f"Could not map parameter type of {repr(v)} to number, string, boolean or json!"
            )

    def fetch_api_data(self, thing: Thing, content: MqttPayload.SyncExtApiT):
        settings = thing.ext_api.settings
        url = settings["endpoint_uri"]
        if urlparse(url).scheme != "https":
            raise NoHttpsError(f"{url} is not https")
        api_key_dec = decrypt(settings["api_key"], get_crypt_key())
        res = request_with_handling(
            "GET",
            url,
            headers={
                "Authorization": f"Bearer {api_key_dec}",
                "Accept": "text/event-stream",
            },
        )
        rep = self.cleanup_json(res.text)
        return {"response": json.loads(rep), "url": url}

    def do_parse(self, api_response):
        bodies = []
        for entry in api_response["response"]:
            msg = entry["result"]["uplink_message"]
            timestamp = msg["received_at"]
            values = msg["decoded_payload"]
            for k, v in values.items():
                if v:
                    result_type = self.dynamic_parameter_mapping(v)
                    body = {
                        "result_time": timestamp,
                        "result_type": result_type,
                        "datastream_pos": k,
                        RESULT_TYPE_MAPPING[result_type]: v,
                        "parameters": json.dumps(
                            {"origin": api_response["url"], "column_header": k}
                        ),
                    }
                    bodies.append(body)
        return {"observations": bodies}

    @staticmethod
    def cleanup_json(string: str) -> str:
        """
        The json string from the TTN Endpoint is erroneous
        and not directly parsable -> remove excess comas
        """
        rep = ",".join(filter(None, string.split("\n")))
        return f"[{rep}]".strip()


class NmApiSyncer(ExtApiSyncer):
    nm_base_url = "http://www.nmdb.eu/nest/draw_graph.php"

    def fetch_api_data(self, thing: Thing, content: MqttPayload.SyncExtApiT):
        settings = thing.ext_api.settings
        start_date = datetime.strptime(content["datetime_from"], "%Y-%m-%d %H:%M:%S")
        end_date = datetime.strptime(content["datetime_to"], "%Y-%m-%d %H:%M:%S")
        params = {
            "wget": 1,
            "stations[]": settings["station_id"],
            "tabchoice": "revori",
            "dtype": "corr_for_efficiency",
            "tresolution": settings["time_resolution"],
            "force": 1,
            "date_choice": "bydate",
            "start_year": {start_date.year},
            "start_month": {start_date.month},
            "start_day": {start_date.day},
            "start_hour": {start_date.hour},
            "start_min": {start_date.min},
            "end_year": {end_date.year},
            "end_month": {end_date.month},
            "end_day": {end_date.day},
            "end_hour": {end_date.hour},
            "end_min": {end_date.min},
            "yunits": 0,
        }
        res = request_with_handling("GET", self.nm_base_url, params=params)
        rows = [
            r.split(";") for r in re.findall(r"^\d.*", res.text, flags=re.MULTILINE)
        ]
        return {
            "response_data": rows,
            "station_id": settings["station_id"],
            "resolution": settings["time_resolution"],
        }

    def do_parse(self, api_response):
        bodies = []
        header = {
            "sensor_id": api_response["station_id"],
            "resolution": api_response["resolution"],
            "nm_api_url": self.nm_base_url,
        }
        for timestamp, value in api_response["response_data"]:
            if value:
                bodies.append(
                    {
                        "result_time": timestamp,
                        "result_type": 0,
                        "datastream_pos": api_response["station_id"],
                        "result_number": float(value),
                        "parameters": json.dumps(
                            {"origin": "nm_data", "column_header": header}
                        ),
                    }
                )
        return {"observations": bodies}


class CustomApiSyncer(ExtApiSyncer):
    """Dynamically loads and delegates to a user-uploaded syncer script."""

    def __init__(self, script_code: str):
        namespace = {"ExtApiSyncer": ExtApiSyncer}
        exec(script_code, namespace)
        syncer_cls = None
        for obj in namespace.values():
            if (
                isinstance(obj, type)
                and issubclass(obj, ExtApiSyncer)
                and obj is not ExtApiSyncer
            ):
                syncer_cls = obj
                break
        if not syncer_cls:
            raise ValueError(
                "Uploaded script does not define an ExtApiSyncer subclass"
            )
        self._delegate = syncer_cls()

    def fetch_api_data(self, thing, content):
        return self._delegate.fetch_api_data(thing, content)

    def do_parse(self, api_response):
        return self._delegate.do_parse(api_response)
