from __future__ import annotations

import json
import logging

import psycopg

from timeio.mqtt import AbstractHandler, MQTTMessage
from timeio.feta import Thing
from timeio.common import get_envvar, setup_logging
from timeio.journaling import Journal
from timeio.typehints import MqttPayload
from timeio.databases import Database

logger = logging.getLogger("mqtt-user-setup")
journal = Journal("System", errors="ignore")


class CreateMqttUserHandler(AbstractHandler):
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
        self.db = Database(get_envvar("DATABASE_URL"))
        self.configdb_dsn = get_envvar("CONFIGDB_DSN")

    def act(self, content: MqttPayload.ConfigDBUpdate, message: MQTTMessage):
        thing = Thing.from_uuid(content["thing"], dsn=self.configdb_dsn)
        user = thing.mqtt.user
        pw = thing.mqtt.password_hashed

        logger.info(f"create user. {user=}")
        created = self.create_user(thing, user, pw)
        action = "Created" if created else "Updated"
        journal.info(f"{action} MQTT user {user}", thing.uuid)

    def create_user(self, thing, user, pw) -> bool:
        """Returns True for insert and False for update"""
        sql = (
            "INSERT INTO mqtt_auth.mqtt_user (project_uuid, thing_uuid, username, "
            "password, description, db_schema) "
            "VALUES (%s, %s, %s, %s ,%s ,%s) "
            "ON CONFLICT (thing_uuid) "
            "DO UPDATE SET"
            " project_uuid = EXCLUDED.project_uuid,"
            " username = EXCLUDED.username,"
            " password=EXCLUDED.password,"
            " description = EXCLUDED.description,"
            " db_schema = EXCLUDED.db_schema "
            "RETURNING (xmax = 0)"
        )
        with self.db.connection() as conn:
            with conn.cursor() as c:
                c.execute(
                    sql,
                    (
                        thing.project.uuid,
                        thing.uuid,
                        user,
                        pw,
                        thing.description,
                        thing.database.username,
                    ),
                )
                return c.fetchone()[0]


if __name__ == "__main__":
    setup_logging(get_envvar("LOG_LEVEL", "INFO"))
    CreateMqttUserHandler().run_loop()
