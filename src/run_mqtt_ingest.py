#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import typing

from paho.mqtt.client import MQTTMessage

from timeio.mqtt import AbstractHandler
from timeio.common import get_envvar, setup_logging
from timeio.errors import UserInputError
from timeio.journaling import Journal
from timeio.databases import DBapi
from timeio.feta import Thing
from timeio.parser import get_parser, MqttParser

logger = logging.getLogger("mqtt-ingest")
journal = Journal("Parser")


class ParseMqttDataHandler(AbstractHandler):
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

        self.configdb_dsn = get_envvar("CONFIGDB_DSN")
        auth_token = get_envvar("DB_API_AUTH_TOKEN")
        self.dbapi = DBapi(
            get_envvar("DB_API_BASE_URL"), auth_token
        )
        logger.info(f"DB_API_AUTH_TOKEN: {auth_token[:4]}***")
        self.pub_topic = get_envvar("TOPIC_DATA_PARSED")

    def act(self, content: typing.Any, message: MQTTMessage):
        origin = f"{self.mqtt_broker}/{message.topic}"

        logger.info(f"get thing")
        mqtt_user = message.topic.split("/")[1]
        thing = Thing.from_mqtt_user_name(mqtt_user, dsn=self.configdb_dsn)
        thing_uuid = thing.uuid

        logger.info(f"get parser")
        parser: MqttParser = get_parser(
            thing.mqtt.mqtt_device_type.name, thing.mqtt.mqtt_device_type.properties
        )

        logger.info(f"parsing rawdata")
        try:
            data = parser.do_parse(content, origin)
            observations = parser.to_observations(data, thing_uuid)
        except Exception as e:
            raise UserInputError("Parsing data failed") from e

        logger.info(f"store observations")
        self.dbapi.upsert_observations(thing_uuid, observations)
        journal.info(f"parsed mqtt data from {origin}", thing_uuid)

        logger.info(f"send mqtt message")
        self.mqtt_client.publish(
            topic=self.pub_topic,
            payload=json.dumps({"thing_uuid": str(thing_uuid)}),
            qos=self.mqtt_qos,
        )


if __name__ == "__main__":
    setup_logging(get_envvar("LOG_LEVEL", "INFO"))
    ParseMqttDataHandler().run_loop()
