#!/usr/bin/env python3
"""
BlueBeatle MQTT WebSocket Bridge
=================================
Subscribes to the BlueBeatle MQTT-over-WebSocket broker and forwards
incoming sensor measurements into the platform's time-series database.

This bridge runs as a single long-lived service. One connection to
wss://api.data.bluebeatle.cz/mqtt covers ALL BlueBeatle places at once
(topic: place/+/data/v3) — far more efficient than per-place HTTP polling.

Auth: OAuth2 Client Credentials (Keycloak, expires every 300s).
The bridge re-connects with a fresh token every TOKEN_REFRESH_INTERVAL seconds.

Place → thing mapping is built at startup from config_db (ext_api where
api_type = 'bluebeatle') and refreshed on each reconnect so newly created
sensors are picked up automatically.

Environment variables:
    BB_CLIENT_ID          OAuth2 client ID (e.g. "czu")
    BB_CLIENT_SECRET      OAuth2 client secret (plaintext)
    CONFIGDB_DSN          PostgreSQL DSN for config_db
    DB_API_BASE_URL       water-dp observation API base URL
    DB_API_AUTH_TOKEN     Bearer token for the observation API
    LOG_LEVEL             Optional, default INFO
    TOKEN_REFRESH_INTERVAL Optional, seconds before reconnect (default 240)
"""

from __future__ import annotations

import json
import logging
import os
import time
import threading
from typing import Any

import psycopg
import paho.mqtt.client as mqtt
import requests

from timeio.common import get_envvar, setup_logging
from timeio.databases import DBapi
from timeio.crypto import decrypt, get_crypt_key

logger = logging.getLogger("bluebeatle-bridge")

BB_HOST = "api.data.bluebeatle.cz"
BB_PORT = 443
BB_MQTT_PATH = "/mqtt"
BB_TOPIC = "place/+/data/v3"
TOKEN_URL = "https://auth.kdejemoje.cz/realms/bb-portal/protocol/openid-connect/token"

# Fields to skip when building observations — not measurements
_SKIP_FIELDS = frozenset({"Imsi", "Timestamp", "ReceivedTime"})


def get_oauth2_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    logger.info("OAuth2 token obtained (expires in 300s)")
    return token


def load_place_mapping(configdb_dsn: str) -> dict[int, str]:
    """
    Query config_db for all things with ext_api type 'bluebeatle'.
    Returns: {place_id (int) -> thing_uuid (str)}
    """
    mapping: dict[int, str] = {}
    with psycopg.connect(configdb_dsn) as conn:
        rows = conn.execute(
            """
            SELECT t.uuid, ea.settings
            FROM config_db.thing t
            JOIN config_db.ext_api ea ON t.ext_api_id = ea.id
            JOIN config_db.ext_api_type eat ON eat.id = ea.api_type_id
            WHERE eat.name = 'bluebeatle'
            """,
        ).fetchall()
    for thing_uuid, settings in rows:
        if not settings:
            continue
        place_id = settings.get("place_id")
        if place_id is not None:
            mapping[int(place_id)] = str(thing_uuid)
    logger.info(f"Loaded {len(mapping)} BlueBeatle place → thing mappings")
    return mapping


def parse_record(record: dict[str, Any], place_id: int) -> list[dict]:
    """Convert a single BlueBeatle JSON record into platform observation dicts."""
    timestamp = record.get("Timestamp")
    if not timestamp:
        return []

    source = {"place_id": place_id, "imsi": record.get("Imsi")}
    params_json = json.dumps({"origin": "bluebeatle_mqtt", "column_header": source})
    observations = []

    for field, value in record.items():
        if field in _SKIP_FIELDS or value is None or value == "":
            continue
        if isinstance(value, bool):
            observations.append({
                "result_time": timestamp,
                "result_type": 3,
                "result_boolean": value,
                "datastream_pos": field,
                "parameters": params_json,
            })
        elif isinstance(value, str):
            observations.append({
                "result_time": timestamp,
                "result_type": 1,
                "result_string": value,
                "datastream_pos": field,
                "parameters": params_json,
            })
        else:
            try:
                observations.append({
                    "result_time": timestamp,
                    "result_type": 0,
                    "result_number": float(value),
                    "datastream_pos": field,
                    "parameters": params_json,
                })
            except (TypeError, ValueError):
                pass

    return observations


WATER_DP_API_URL = os.getenv("WATER_DP_API_URL", "http://water-dp-api:8000")


def _record_activity(thing_uuid: str) -> None:
    """Notify the water-dp API that this sensor is active so last_seen_at is updated."""
    try:
        url = f"{WATER_DP_API_URL}/api/v1/alerts/record-activity/{thing_uuid}"
        requests.post(url, timeout=5)
    except Exception:
        logger.warning("Failed to record activity for %s (activity won't be tracked this cycle)", thing_uuid)


class BlueBeatbleBridge:
    def __init__(self):
        self.client_id = get_envvar("BB_CLIENT_ID")
        self.client_secret = get_envvar("BB_CLIENT_SECRET")
        self.configdb_dsn = get_envvar("CONFIGDB_DSN")
        self.token_refresh_interval = int(
            os.getenv("TOKEN_REFRESH_INTERVAL", "240")
        )
        self.dbapi = DBapi(
            get_envvar("DB_API_BASE_URL"),
            get_envvar("DB_API_AUTH_TOKEN"),
        )
        self.place_to_thing: dict[int, str] = {}
        self._stop_event = threading.Event()

    def _make_client(self, token: str) -> mqtt.Client:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="bb-bridge",
            transport="websockets",
        )
        client.tls_set()
        client.ws_set_options(path=BB_MQTT_PATH)
        client.username_pw_set("bridge", token)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        return client

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info(f"Connected to BlueBeatle MQTT broker at {BB_HOST}")
            client.subscribe(BB_TOPIC, qos=0)
            logger.info(f"Subscribed to {BB_TOPIC}")
        else:
            logger.error(f"MQTT connect failed, reason code: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        logger.info(f"Disconnected from BlueBeatle MQTT (reason={reason_code})")

    def _on_message(self, client, userdata, message: mqtt.MQTTMessage):
        try:
            # Topic format: place/<placeId>/data/v3
            parts = message.topic.split("/")
            if len(parts) < 2:
                return
            place_id = int(parts[1])

            thing_uuid = self.place_to_thing.get(place_id)
            if not thing_uuid:
                # Unknown place — not registered in the platform
                logger.debug(f"No thing mapped for place_id={place_id}, skipping")
                return

            record = json.loads(message.payload.decode("utf-8"))
            observations = parse_record(record, place_id)

            if not observations:
                return

            self.dbapi.upsert_observations(thing_uuid, observations)
            _record_activity(thing_uuid)
            logger.info(
                f"place_id={place_id} → thing={thing_uuid}: "
                f"stored {len(observations)} observations"
            )
        except Exception:
            logger.exception(f"Error processing message on {message.topic}")

    def run(self) -> None:
        logger.info("BlueBeatle MQTT bridge starting")
        while not self._stop_event.is_set():
            try:
                # Refresh place mapping on every reconnect (picks up new sensors)
                self.place_to_thing = load_place_mapping(self.configdb_dsn)

                token = get_oauth2_token(self.client_id, self.client_secret)
                client = self._make_client(token)
                client.connect(BB_HOST, BB_PORT, keepalive=60)
                client.loop_start()

                # Run until token nears expiry, then reconnect with a fresh one
                self._stop_event.wait(timeout=self.token_refresh_interval)

                client.disconnect()
                client.loop_stop()
                logger.info("Token refresh cycle: reconnecting with new token")

            except requests.HTTPError as e:
                logger.error(f"Failed to obtain OAuth2 token: {e} — retrying in 30s")
                time.sleep(30)
            except Exception:
                logger.exception("Unexpected error in bridge loop — retrying in 10s")
                time.sleep(10)

        logger.info("BlueBeatle MQTT bridge stopped")


if __name__ == "__main__":
    setup_logging(get_envvar("LOG_LEVEL", "INFO"))
    BlueBeatbleBridge().run()
