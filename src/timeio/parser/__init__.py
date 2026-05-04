from __future__ import annotations

from typing import Any

from timeio.parser.abc_parser import AbcParser
from timeio.parser.pandas_parser import PandasParser
from timeio.parser.csv_parser import CsvParser
from timeio.parser.json_parser import JsonParser
from timeio.parser.mqtt_parser import MqttParser
from timeio.parser.mqtt_devices.brightsky_dwd import BrightskyDwdApiParser
from timeio.parser.mqtt_devices.campbell_cr6 import CampbellCr6Parser
from timeio.parser.mqtt_devices.chirpstack_generic import ChirpStackGenericParser
from timeio.parser.mqtt_devices.ydoc_ml_417 import YdocMl417Parser
from timeio.parser.mqtt_devices.sine_dummy import SineDummyParser

_parser_map = {
    "csvparser": CsvParser,
    "jsonparser": JsonParser,
    "campbell_cr6": CampbellCr6Parser,
    "brightsky_dwd_api": BrightskyDwdApiParser,
    "ydoc_ml417": YdocMl417Parser,
    "chirpstack_generic": ChirpStackGenericParser,
    "sine_dummy": SineDummyParser,
}

_default_settings = {
    CsvParser: {
        "comment": "#",
        "decimal": ".",
        "na_values": None,
        "encoding": "utf-8",
        "engine": "python",
        "on_bad_lines": "warn",
        "header": None,
    },
    JsonParser: {
        "timestamp_keys": [{"key": "Datetime", "format": "%Y-%m-%dT%H:%M:%S"}],
    },
}


def get_parser(
    parser_type: str, settings: dict[str, Any] | None
) -> CsvParser | JsonParser | MqttParser:
    """Get initialized parser by name."""

    klass = _parser_map.get(parser_type)
    if klass is None:
        raise NotImplementedError(f"parser {parser_type!r} not known")

    settings = settings or {}
    default_settings = _default_settings.get(klass, {})

    if issubclass(klass, CsvParser):
        pd_kws = settings.pop("pandas_read_csv", None) or {}
        settings = {**default_settings, **settings, **pd_kws}
        instance = klass(settings)

    elif issubclass(klass, JsonParser):
        settings = {**default_settings, **settings}
        norm_kws = settings.pop("pandas_json_normalize", {})
        instance = klass(settings, norm_kws)

    elif issubclass(klass, MqttParser):
        # Instantiate MQTT device parsers (e.g., ChirpStackGenericParser)
        instance = klass()

    else:
        # Fallback: Dynamic loading for custom parsers
        # If settings contain script info, try to load dynamically
        if settings and settings.get("script_bucket") and settings.get("script_path"):
            try:
                from timeio.parser.dynamic_loader import load_dynamic_parser
                klass = load_dynamic_parser(
                    settings["script_bucket"], settings["script_path"]
                )
                instance = klass()
                return instance
            except ImportError as e:
                # If dynamic loading fails, re-raise as NotImplemented or log?
                # For now, let it bubble up or wrap it.
                # raising NotImplementedError to match signature expectation if not found
                raise NotImplementedError(f"Dynamic parser loading failed: {e}")

        # If we are here, we really don't know the parser
        raise NotImplementedError(f"parser {parser_type!r} not known")

    return instance
