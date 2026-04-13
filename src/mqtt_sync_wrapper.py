#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import click
import json
import psycopg

from datetime import datetime, timedelta, timezone


from timeio.mqtt import publish_single
from timeio.feta import Thing
from timeio.common import get_envvar
from timeio.crypto import decrypt, get_crypt_key


def get_tsystems_timerange(thing):
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp_from = now_utc - timedelta(minutes=60)
    timestamp_from_str = timestamp_from.strftime("%Y-%m-%dT%H:%M:%SZ")
    return timestamp_from_str, now_str


def get_bosch_timerange(thing):
    settings = thing.ext_api.settings
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp_from = now_utc - timedelta(minutes=settings["period"])
    timestamp_from_str = timestamp_from.strftime("%Y-%m-%dT%H:%M:%SZ")
    return timestamp_from_str, now_str


def get_dwd_timerange(thing):
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_start = datetime.strftime(yesterday, "%Y-%m-%dT00:00:00")
    yesterday_end = datetime.strftime(yesterday, "%Y-%m-%dT23:55:00")
    return yesterday_start, yesterday_end


def get_uba_timerange(thing):
    """UBA API expects time_from/time_to in the range of 1 to 24"""
    datetime_now = datetime.now()
    datetime_from = datetime_now - timedelta(hours=1)
    if datetime_now.hour == 0:
        datetime_to = (datetime_now - timedelta(days=1)).strftime(
            "%Y-%m-%d"
        ) + " 24:00:00"
    else:
        datetime_to = datetime_now.strftime("%Y-%m-%d") + f" {datetime_now.hour}:00:00"
    if datetime_from.hour == 0:
        datetime_from = (datetime_from - timedelta(days=1)).strftime(
            "%Y-%m-%d"
        ) + " 24:00:00"
    else:
        datetime_from = (
            datetime_from.strftime("%Y-%m-%d") + f" {datetime_from.hour}:00:00"
        )
    return datetime_from, datetime_to


def get_nm_timerange(thing):
    db = thing.project.database
    db_pw = decrypt(db.password, get_crypt_key())
    dsn = f"postgresql://{db.user}:{db_pw}@{get_envvar('DB_HOST')}/{get_envvar('DB_NAME')}"
    start_date = datetime(2000, 1, 1)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(o.result_time)
                FROM observation o
                JOIN datastream d ON o.datastream_id = d.id
                JOIN thing t ON d.thing_id = t.id
                WHERE t.uuid = %s
                """,
                (thing.uuid,),
            )
            date = cur.fetchone()[0]
            if date:
                start_date = date
    return start_date.strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def get_default_timerange(thing):
    """Default time range: last 24 hours. Used for custom API types."""
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")


TIMERANGE_MAPPING = {
    "tsystems": get_tsystems_timerange,
    "bosch": get_bosch_timerange,
    "dwd": get_dwd_timerange,
    "ttn": get_dwd_timerange,
    "uba": get_uba_timerange,
    "nm": get_nm_timerange,
}


@click.group()
def cli():
    pass


@cli.command()
@click.argument("thing_uuid")
def sync_thing(thing_uuid: str):
    thing = Thing.from_uuid(thing_uuid, dsn=get_envvar("CONFIGDB_DSN"))
    if thing.ext_api is not None:
        ext_api_name = thing.ext_api.api_type_name
        timerange_fn = TIMERANGE_MAPPING.get(ext_api_name, get_default_timerange)
        datetime_from, datetime_to = timerange_fn(thing)
        message = {
            "thing": thing.uuid,
            "datetime_from": datetime_from,
            "datetime_to": datetime_to,
        }
        publish_single(get_envvar("API_SYNC_TOPIC"), json.dumps(message))
    elif thing.ext_sftp is not None:
        message = {"thing": thing.uuid}
        publish_single(get_envvar("SFTP_SYNC_TOPIC"), json.dumps(message))


@cli.command()
@click.argument("origin")
def sync_sms(origin: str):
    message = {"origin": origin}
    publish_single(get_envvar("SMS_SYNC_TOPIC"), json.dumps(message))


@cli.command()
def mqtt_monitoring():
    publish_single(get_envvar("MQTT_MONITORING_TOPIC"), json.dumps({}))


if __name__ == "__main__":
    cli()
