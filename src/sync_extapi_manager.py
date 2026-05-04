from __future__ import annotations

import logging
import requests
import json

from requests.exceptions import HTTPError

from timeio.mqtt import AbstractHandler, MQTTMessage
from timeio.common import get_envvar, setup_logging
from timeio.feta import Thing
from timeio.typehints import MqttPayload
from timeio.journaling import Journal
from timeio.ext_api import (
    BoschApiSyncer,
    TsystemsApiSyncer,
    UbaApiSyncer,
    DwdApiSyncer,
    TtnApiSyncer,
    NmApiSyncer,
    CustomApiSyncer,
    ExtApiRequestError,
    NoHttpsError,
)

logger = logging.getLogger("sync-extapi-manager")
journal = Journal("sync_ext_apis")


class SyncExtApiManager(AbstractHandler):

    def __init__(self):
        super().__init__(
            topic=get_envvar("TOPIC"),
            mqtt_broker=get_envvar("MQTT_BROKER"),
            mqtt_user=get_envvar("MQTT_USER"),
            mqtt_password=get_envvar("MQTT_PASSWORD"),
            mqtt_client_id=get_envvar("MQTT_CLIENT_ID"),
            mqtt_qos=get_envvar("MQTT_QOS", cast_to=int),
            mqtt_clean_session=get_envvar("MQTT_CLEAN_SESSION", cast_to=bool),
        )
        self.api_base_url = get_envvar("DB_API_BASE_URL")
        self.api_token = get_envvar("DB_API_AUTH_TOKEN")
        self.configdb_dsn = get_envvar("CONFIGDB_DSN")
        self.sync_handlers = {
            "tsystems": TsystemsApiSyncer(),
            "bosch": BoschApiSyncer(),
            "uba": UbaApiSyncer(),
            "dwd": DwdApiSyncer(),
            "ttn": TtnApiSyncer(),
            "nm": NmApiSyncer(),
        }
        self._custom_syncer_cache = {}

    def _load_custom_syncer(self, api_type_name: str):
        """Load a custom syncer script from MinIO via ext_api_type.properties."""
        if api_type_name in self._custom_syncer_cache:
            return self._custom_syncer_cache[api_type_name]

        import psycopg

        with psycopg.connect(self.configdb_dsn) as conn:
            row = conn.execute(
                "SELECT properties FROM config_db.ext_api_type WHERE name = %s",
                [api_type_name],
            ).fetchone()

        if not row or not row[0]:
            raise ValueError(
                f"No custom syncer configured for API type '{api_type_name}'"
            )

        properties = row[0]
        script_bucket = properties.get("script_bucket")
        script_path = properties.get("script_path")
        if not script_bucket or not script_path:
            raise ValueError(
                f"API type '{api_type_name}' has no syncer script configured"
            )

        from minio import Minio

        minio_client = Minio(
            get_envvar("MINIO_URL"),
            access_key=get_envvar("MINIO_USER"),
            secret_key=get_envvar("MINIO_PASSWORD"),
            secure=False,
        )
        response = minio_client.get_object(script_bucket, script_path)
        script_code = response.read().decode("utf-8")
        response.close()
        response.release_conn()

        syncer = CustomApiSyncer(script_code)
        self._custom_syncer_cache[api_type_name] = syncer
        logger.info(f"Loaded custom syncer for API type '{api_type_name}'")
        return syncer

    def act(self, content: MqttPayload.SyncExtApiT, message: MQTTMessage):
        thing = Thing.from_uuid(content["thing"], dsn=self.configdb_dsn)
        ext_api_name = thing.ext_api.api_type_name

        if ext_api_name in self.sync_handlers:
            syncer = self.sync_handlers[ext_api_name]
        else:
            try:
                syncer = self._load_custom_syncer(ext_api_name)
            except Exception as e:
                journal.error(
                    f"Failed to load custom syncer for '{ext_api_name}': {e}",
                    thing.uuid,
                )
                return

        try:
            data = syncer.fetch_api_data(thing, content)
        except (ExtApiRequestError, NoHttpsError) as e:
            journal.error(e.msg, thing.uuid)
            return
        try:
            obs = syncer.do_parse(data)
            self.write_observations(thing, obs)

        except HTTPError as e:
            journal.error(
                f"Insert/upsert into timeioDB for thing '{thing.name} failed",
                thing.uuid,
            )
            raise e
        except Exception as e:
            journal.error(
                f"Error in processing data for thing '{thing.name}", thing.uuid
            )
            raise e

        self.mqtt_client.publish(
            topic="data_parsed",
            payload=json.dumps({"thing_uuid": thing.uuid}),
        )
        journal.info(
            f"Successfully inserted {len(obs['observations'])} "
            f"observations from API '{ext_api_name}' "
            f"for thing '{thing.name}' into timeIO DB",
            thing.uuid,
        )

    def write_observations(self, thing: Thing, parsed_observations: dict):
        resp = requests.post(
            f"{self.api_base_url}/observations/upsert/{thing.uuid}",
            json=parsed_observations,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_token}",
            },
        )
        resp.raise_for_status()


if __name__ == "__main__":
    setup_logging(get_envvar("LOG_LEVEL", "INFO"))
    SyncExtApiManager().run_loop()
