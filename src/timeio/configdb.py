#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
from uuid import uuid5, NAMESPACE_DNS
from typing import Any, Literal, Sequence, cast, Optional

from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from timeio.common import get_envvar, get_envvar_as_bool
from timeio.typehints import MqttPayload

logger = logging.getLogger("configdb-updater")

if get_envvar_as_bool("DEBUG_SQL"):
    import timeioutils.psycopg_helper as _help

    _l = get_envvar("LOG_LEVEL", "DEBUG")
    _help.monkey_patch_psycopg_execute_to_log_sql_queries(logger, log_level=_l)
    del _help, _l


_IDS_BY_UUID_QUERY = sql.SQL("""\
SELECT t.id as thing_id, t.project_id, p.database_id, t.ingest_type_id, t.s3_store_id,
s3s.file_parser_id, fp.file_parser_type_id, t.mqtt_id, m.mqtt_device_type_id,
t.ext_sftp_id, t.ext_api_id, ea.api_type_id
FROM config_db.thing t
LEFT JOIN config_db.project p ON t.project_id = p.id
LEFT JOIN config_db.s3_store s3s ON t.s3_store_id = s3s.id
LEFT JOIN config_db.file_parser fp ON s3s.file_parser_id = fp.id
LEFT JOIN config_db.mqtt m ON t.mqtt_id = m.id
LEFT JOIN config_db.ext_api ea ON t.ext_api_id = ea.id
WHERE t.uuid = %s
""")
_no_ids = {
    "thing_id": None,
    "project_id": None,
    "database_id": None,
    "ingest_type_id": None,
    "s3_store_id": None,
    "file_parser_id": None,
    "file_parser_type_id": None,
    "mqtt_id": None,
    "mqtt_device_type_id": None,
    "ext_sftp_id": None,
    "ext_api_id": None,
    "api_type_id": None,
}


def fetch_thing_related_ids(conn: Connection, thing_uuid: str) -> dict[str, int | None]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(_IDS_BY_UUID_QUERY, [thing_uuid]).fetchone() or _no_ids


def fetch_project_related_ids(
    conn: Connection, project_uuid: str
) -> dict[str, int | None]:
    q = (
        "select p.id as project_id, p.database_id "
        "from config_db.project p where p.uuid = %s"
    )
    no_ids = {"project_id": None, "database_id": None}
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(q, [project_uuid]).fetchone() or no_ids


def upsert_schema_thing_mapping(conn: Connection, uuid: str, schema: str):
    # This ensures that we don't compare
    # None to None later at the early exit.
    if schema is None:
        raise ValueError("schema must not be None")

    q = "SELECT schema FROM public.schema_thing_mapping WHERE thing_uuid=%s"
    curr_schema = conn.execute(cast(Literal, q), [uuid]).fetchone()

    if curr_schema is not None:
        curr_schema = curr_schema[0]

    if curr_schema == schema:
        logger.debug(f"thing:schema mapping already exists")
        return

    q = (
        "INSERT INTO public.schema_thing_mapping (schema, thing_uuid) "
        "VALUES (%s::varchar(100), %s::uuid) "
        "ON CONFLICT (schema, thing_uuid) DO UPDATE SET "
        "schema = EXCLUDED.schema, "
        "thing_uuid = EXCLUDED.thing_uuid "
    )
    conn.execute(cast(Literal, q), [schema, uuid])
    if curr_schema is None:
        logger.info(f"created thing:schema mapping in DB for thing {uuid}")
    else:
        logger.info(f"updated thing:schema mapping in DB for thing {uuid}")


def maybe_inform_unused_keys(v: dict):
    if v:
        logger.debug(f"unused keys: {list(v.keys())}", stacklevel=2)


def fetch_ingest_type_id(conn: Connection, name: str) -> int:
    """Returns the ID of an ingest type, selected by its name."""
    name = name.lower()
    r = conn.execute(
        "SELECT it.id FROM config_db.ingest_type it WHERE it.name = %s",
        [name],
    ).fetchone()
    if r is None:
        raise ValueError(f"No entry for ingest_type {name!r}")
    return r[0]


def fetch_parser_type_id(conn: Connection, name: str) -> int:
    """Returns the ID of a file parser type, selected by its name."""
    name = name.lower()
    r = conn.execute(
        "SELECT fpt.id FROM config_db.file_parser_type fpt WHERE fpt.name = %s",
        [name],
    ).fetchone()
    if r is None:
        raise ValueError(f"No entry for parser_type {name!r}")
    return r[0]


def fetch_device_type_id(conn: Connection, name: str) -> int:
    """Returns the ID of a mqtt device type, selected by its name."""
    name = name.lower()
    r = conn.execute(
        "SELECT mdt.id FROM config_db.mqtt_device_type mdt WHERE mdt.name = %s",
        [name],
    ).fetchone()
    if r is None:
        logger.info(f"Device type '{name}' not found. Auto-creating.")
        r = conn.execute(
            "INSERT INTO config_db.mqtt_device_type (name) VALUES (%s) RETURNING id",
            [name],
        ).fetchone()
    return r[0]


def fetch_extapi_type_id(conn: Connection, name: str) -> int:
    """Returns the ID of an external api type, selected by its name."""
    name = name.lower()
    r = conn.execute(
        "SELECT eat.id FROM config_db.ext_api_type eat WHERE eat.name = %s",
        [name],
    ).fetchone()
    if r is None:
        raise ValueError(f"No entry for ext_api_type {name!r}")
    return r[0]


def fetch_project_id(conn: Connection, proj_uuid: str) -> int:
    """Returns the ID of a project, selected by its UUID."""
    r = conn.execute(
        "SELECT p.id FROM config_db.project p WHERE p.uuid = %s", [proj_uuid]
    ).fetchone()
    if r is None:
        raise ValueError(f"No entry for project with UUID {proj_uuid!r}")
    return r[0]


def fetch_qaqc_id(conn: Connection, proj_id: int, qaqc_name: str) -> int | None:
    """
    Returns the ID of a qaqc config, selected by a given
    project ID and the name of the qaqc config.

    Returns None if qaqc config does not exist.
    """
    r = conn.execute(
        "SELECT q.id FROM config_db.qaqc q WHERE q.project_id = %s and q.name = %s",
        [proj_id, qaqc_name],
    ).fetchone()
    if r is not None:
        r = r[0]
    return r


def _upsert(
    conn: Connection,
    table: str,
    columns: Sequence[str],
    values: Sequence[Any],
    id: int | None = None,
    schema: str = "config_db",
    on_conflict_column: Optional[str] = None,
):
    """
    Either execute insert [1] or update [2] on DB, depending on if the
    given id is None or an existing ID respectively.

    [1] INSERT INTO table (column1, column2, ...) VALUES (%s, %s, ...)
        [ ON CONFLICT confl_col DO UPDATE SET confl_col = EXCLUDED.confl_col ]
        The ON-CONFLICT part is optional.
    [2] UPDATE table t SET column1 = %s, column2 = %s, ... WHERE t.id = %s

    Note that `on_conflict_column` is ignored if `id` is an integer.
    """
    q = "INSERT INTO {table} ({columns}) VALUES ({values})"
    q_insert = sql.SQL(q).format(
        table=sql.Identifier(schema, table),
        columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
        values=sql.SQL(", ").join(sql.Placeholder() * len(columns)),
    )
    q = "UPDATE {table} t SET {mapping} WHERE t.id = %s RETURNING t.id"
    q_update = sql.SQL(q).format(
        table=sql.Identifier(schema, table),
        mapping=sql.SQL(", ").join(
            [sql.SQL("{col} = %s").format(col=sql.Identifier(col)) for col in columns]
        ),
    )
    if on_conflict_column:
        q_insert += sql.SQL(
            "ON CONFLICT ({col}) DO UPDATE SET {col} = EXCLUDED.{col}"
        ).format(col=sql.Identifier(on_conflict_column))

    q_insert += sql.SQL("RETURNING id")
    q_insert = q_insert.join(" ").as_string()
    values = [Jsonb(v) if isinstance(v, dict) else v for v in values]

    if id is None:
        query = q_insert
        logger.debug(f"Try inserting new values to {schema}.{table}")
    else:
        values.append(id)
        query = q_update
        logger.debug(f"Try updating values of {schema}.{table} with id {id}")
    r = conn.execute(query, values).fetchone()
    return r[0]


def upsert_table_database(conn: Connection, values: dict, db_id: int | None) -> int:
    #     "database": {
    #         "username": db.username,
    #         "password": db.password,
    #         "url": get_connection_string(thing),
    #         "ro_username": db.ro_username,
    #         "ro_password": db.ro_password,
    #         "ro_url": get_connection_string(thing, readonly=True),
    v = values.copy()
    id_ = _upsert(
        conn,
        table="database",
        columns=[
            "schema",
            "user",
            "password",
            "ro_user",
            "ro_password",
            "url",
            "ro_url",
        ],
        values=[
            v.pop("schema"),
            v.pop("username"),
            v.pop("password"),
            v.pop("ro_username"),
            v.pop("ro_password"),
            v.pop("url"),
            v.pop("ro_url"),
        ],
        id=db_id,
    )
    maybe_inform_unused_keys(v)
    return id_


def upsert_table_file_parser(conn: Connection, values: dict, fp_id: int | None) -> int:
    #            type : <someType>
    #            settings: {
    #               "delimiter": self.delimiter,
    #               "skipfooter": self.exclude_footlines,
    #               "skiprows": self.exclude_headlines,
    #               "timestamp_column": self.timestamp_column,
    #               "timestamp_format": self.timestamp_format,
    #               "pandas_read_csv": self.pandas_read_csv,
    #             }
    v = values.copy()
    type_id = fetch_parser_type_id(conn, v.pop("type"))

    id_ = _upsert(
        conn,
        table="file_parser",
        columns=["file_parser_type_id", "name", "params", "uuid"],
        values=[type_id, v.pop("name"), v.pop("settings"), v.pop("uuid")],
        id=fp_id,
        on_conflict_column="uuid",
    )
    maybe_inform_unused_keys(v)
    return id_


def upsert_table_project(
    conn: Connection, values: dict, db_id: int, proj_id: int | None
) -> int:
    #     "project": {
    #         "name": get_group_name_with_vo_prefix(thing.group),
    #         "uuid": str(uuid.UUID(int=thing.group.id)),
    v = values.copy()
    id_ = _upsert(
        conn,
        table="project",
        columns=["name", "uuid", "database_id"],
        values=[v.pop("name"), v.pop("uuid"), db_id],
        id=proj_id,
        on_conflict_column="uuid",
    )
    maybe_inform_unused_keys(v)
    return id_


def upsert_table_s3_store(
    conn: Connection, values: dict, parser_id: int, s3_id: int | None
) -> int:
    #     "raw_data_storage":
    #         "bucket_name": storage.bucket,
    #         "username": storage.access_key,
    #         "password": storage.secret_key,
    #         "filename_pattern": thing.sftp_filename_pattern,
    v = values.copy()
    id_ = _upsert(
        conn,
        table="s3_store",
        columns=("user", "password", "bucket", "filename_pattern", "file_parser_id"),
        values=(
            v.pop("username"),
            v.pop("password"),
            v.pop("bucket_name"),
            v.pop("filename_pattern"),
            parser_id,
        ),
        id=s3_id,
    )
    maybe_inform_unused_keys(v)
    return id_


def upsert_table_mqtt(conn: Connection, values: dict, mqtt_id: int | None) -> int:
    #         mqtt_device_type: None or name
    #         "username": thing.mqtt_username,
    #         "password_hash": thing.mqtt_hashed_password,
    #         "description": thing.mqtt_topic,
    #         "properties": thing.mqtt_uri,
    v = values.copy()
    dev_type_id = None
    if dev_type_name := v.pop("mqtt_device_type"):
        dev_type_id = fetch_device_type_id(conn, dev_type_name)
    id_ = _upsert(
        conn,
        table="mqtt",
        columns=("user", "password", "password_hashed", "topic", "mqtt_device_type_id"),
        values=(
            v.pop("username"),
            v.pop("password"),
            v.pop("password_hash"),
            v.pop("topic"),
            dev_type_id,
        ),
        id=mqtt_id,
    )
    maybe_inform_unused_keys(v)
    return id_


def upsert_table_ext_sftp(conn: Connection, values: dict, extftp_id) -> int:
    #     "external_sftp": {
    #         "sync_enabled": thing.ext_sftp_sync_enabled
    #         "uri": thing.ext_sftp_uri,
    #         "path": thing.ext_sftp_path,
    #         "username": thing.ext_sftp_username,
    #         "password": thing.ext_sftp_password or None
    #         "sync_interval": thing.ext_sftp_sync_interval,
    #         "public_key": thing.ext_sftp_public_key,
    #         "private_key": encrypted private ssh key or "" (empty string),
    v = values.copy()
    id_ = _upsert(
        conn,
        table="ext_sftp",
        columns=(
            "uri",
            "path",
            "user",
            "password",
            "ssh_priv_key",
            "ssh_pub_key",
            "sync_interval",
            "sync_enabled",
        ),
        values=(
            v.pop("uri"),
            v.pop("path"),
            v.pop("username"),
            v.pop("password"),  # can be None
            v.pop("private_key"),
            v.pop("public_key"),
            v.pop("sync_interval"),
            v.pop("sync_enabled"),
        ),
        id=extftp_id,
    )
    maybe_inform_unused_keys(v)
    return id_


def upsert_table_ext_api(conn: Connection, values: dict, api_id: int | None) -> int:
    #   "external_api":
    #       type : str or None
    #       enabled: bool or None
    #       sync_interval: str or None
    #       settings: {"version": 1} or None
    #
    v = values.copy()
    type_id = None
    if typ := v.pop("type"):
        type_id = fetch_extapi_type_id(conn, typ)

    id_ = _upsert(
        conn,
        table="ext_api",
        columns=("api_type_id", "sync_interval", "sync_enabled", "settings"),
        values=(type_id, v.pop("sync_interval"), v.pop("enabled"), v.pop("settings")),
        id=api_id,
    )
    maybe_inform_unused_keys(v)
    return id_


def upsert_table_thing(
    conn: Connection,
    uuid: str,
    name: str,
    proj_id: int,
    ingest_type_id: int,
    s3_id: int,
    mqtt_id: int,
    sftp_id: int,
    api_id: int,
    thing_id: int | None,
    description: str,
    qid: int | None,
) -> int:
    id_ = _upsert(
        conn,
        table="thing",
        columns=(
            "uuid",
            "name",
            "project_id",
            "ingest_type_id",
            "s3_store_id",
            "mqtt_id",
            "ext_sftp_id",
            "ext_api_id",
            "description",
            "legacy_qaqc_id",
        ),
        values=(
            uuid,
            name,
            proj_id,
            ingest_type_id,
            s3_id,
            mqtt_id,
            sftp_id,
            api_id,
            description,
            qid,
        ),
        id=thing_id,
    )
    return id_


def store_project_config(conn: Connection, data: dict):
    ids = fetch_project_related_ids(conn, data["project"]["uuid"])
    db_id = upsert_table_database(conn, data["database"], ids["database_id"])
    pid = upsert_table_project(conn, data["project"], db_id, ids["project_id"])
    return pid


def store_thing_config(conn: Connection, data: dict, qid: int | None, proj_id: int):
    # version: 4,
    # uuid: <str/uuid>
    # name: <str>
    # description: <str>
    # project: {...}
    # ingest_type: <str>
    # database: {...}
    # qaqc: {...}
    # parsers:
    #    default: <int> (index into parsers)
    #    parsers: [ {...}, {...} ]
    # mqtt_device_type: <str or None>
    # raw_data_storage: {...}
    # mqtt: {...}
    # external_sftp: {...}
    # external_api: {...}
    uuid = data["uuid"]
    name = data["name"]
    proj_uuid = data["project"]["uuid"]
    schema = data["database"]["schema"]
    upsert_schema_thing_mapping(conn, uuid, schema)
    ids = fetch_thing_related_ids(conn, uuid)

    ingest_type = data["ingest_type"].lower()
    ingest_type_id = fetch_ingest_type_id(conn, ingest_type)

    mqtt_id = None
    if mqtt := data["mqtt"]:
        mqtt_id = upsert_table_mqtt(conn, mqtt, ids["mqtt_id"])

    sftp_id = None
    if ext_sftp := data["external_sftp"]:
        sftp_id = upsert_table_ext_sftp(conn, ext_sftp, ids["ext_sftp_id"])

    api_id = None
    if ext_api := data["external_api"]:
        api_id = upsert_table_ext_api(conn, ext_api, ids["ext_api_id"])

    parser_id = None
    if parsers := data["parsers"]:
        idx = parsers["default"]
        parser = parsers["parsers"][idx]
        uuid_base = f"{parser['name']}{proj_uuid}"
        parser_uuid = uuid5(NAMESPACE_DNS, uuid_base)
        parser["uuid"] = parser_uuid
        parser_id = upsert_table_file_parser(conn, parser, ids["file_parser_id"])

    s3_id = None
    if s3 := data["raw_data_storage"]:
        s3_id = upsert_table_s3_store(conn, s3, parser_id, ids["s3_store_id"])

    upsert_table_thing(
        conn,
        uuid,
        name,
        proj_id,
        ingest_type_id,
        s3_id,
        mqtt_id,
        sftp_id,
        api_id,
        ids["thing_id"],
        data["description"],
        qid,
    )


# ===================================================================
# QAQC related stuff
# ===================================================================
# Qaqc lives in its own tables and is not strongly coupled to a thing.
# Things and qaqc-configs are connected by a Project.
# Briefly:
#   - a PROJECT can have multiple THINGs
#   - a PROJECT can have multiple QAQC_CONFIGs
#   - a THING has to have a PROJECT
#   - a QAQC_CONFIG has to have a PROJECT
# ===================================================================


def upsert_table_qaqc(
    conn: Connection, values: dict, proj_id: int, qaqc_id: int | None
) -> int:
    #   type : "SaQC",
    #   name: "MyConfig",
    #   context_window: str or int,
    #   default: bool
    #   tests: [...]  # we ignore those for now
    v = values.copy()
    v.pop("tests", None)  # v1
    v.pop("functions", None)  # v2
    # in versions < 3 we don't have the default field,
    # and each new QC Settings are considered to be
    # the new default
    v.setdefault("default", True)
    id_ = _upsert(
        conn,
        table="qaqc",
        columns=("name", "project_id", "context_window", "default"),
        values=(v.pop("name"), proj_id, v.pop("context_window"), v.pop("default")),
        id=qaqc_id,
    )
    maybe_inform_unused_keys(v)
    return id_


def delete_qaqc_tests(conn: Connection, qaqc_id: int) -> int:
    """
    Deletes every qaqc test that belongs to a given qaqc config (ID).
    Returns the number of deleted tests.
    """
    q = (
        "WITH deleted AS ("
        "DELETE FROM config_db.qaqc_test qt WHERE qt.qaqc_id = %s RETURNING *"
        ") SELECT count(*) FROM deleted"
    )
    return conn.execute(cast(Literal, q), [qaqc_id]).fetchone()[0]


def insert_qaqc_tests(
    conn: Connection,
    qaqc_id: int,
    tests: list[MqttPayload.QaqcTestT] | list[MqttPayload.QaqcFunctionT],
    version: int,
):
    """
    Insert multiple qaqc tests that belong to a qaqc config.
    Returns the number of inserted tests.
    """
    n = 0
    q = "COPY config_db.qaqc_test (qaqc_id, name, function, args, streams, position) FROM STDIN"
    with conn.cursor() as cur:
        with cur.copy(q) as copy:
            for n, test in enumerate(tests):
                if version == 1:
                    test: MqttPayload.QaqcTestT
                    copy.write_row(
                        [
                            qaqc_id,
                            f"Test {n+1}",
                            test["function"],
                            Jsonb(test["kwargs"]),
                            None,
                            test["position"],
                        ]
                    )
                elif version in (2, 3):
                    test: MqttPayload.QaqcFunctionT

                    # workaround for missing parsing in frontend
                    if test["func_id"] == "freetext":
                        raw = test["kwargs"]["function"]
                        jraw = json.loads(raw)
                        test["func_id"] = jraw.get("func", "unparsableFunction")
                        test["kwargs"] = jraw.get("kwargs", {})

                    copy.write_row(
                        [
                            qaqc_id,
                            test["name"],
                            test["func_id"],
                            Jsonb(test["kwargs"]),
                            Jsonb(test["datastreams"]),
                            None,
                        ]
                    )
                else:
                    raise ValueError(f"Unknown QC-Test version: {version}")
    return n


def store_qaqc_config(conn: Connection, data: dict, legacy: bool):
    version = data["version"]
    proj_uuid = data["project_uuid"]
    qaqc_name = data["name"]

    def check_keys(test, nr, keys):
        for key in keys:
            if key not in test:
                raise ValueError(f"missing key {key!r} in saqc test number {nr}")

    # adjust to latest version
    if version == 1:
        data: MqttPayload.QaqcConfigV1_T
        tests = data["tests"]
        for i, test in enumerate(tests):
            check_keys(test, i + 1, ["function", "kwargs", "position"])

    elif version == 2:
        data: MqttPayload.QaqcConfigV2_T
        tests = data["functions"]
        for i, test in enumerate(tests):
            check_keys(test, i + 1, ["name", "func_id", "kwargs", "datastreams"])

    elif version == 3:
        data: MqttPayload.QaqcConfigV3_T
        tests = data["functions"]
        for i, test in enumerate(tests):
            check_keys(test, i + 1, ["name", "func_id", "kwargs", "datastreams"])

    else:
        raise NotImplementedError(
            f"Qaqc config protokoll version {version} is not yet implemented."
        )
    pid = fetch_project_id(conn, proj_uuid)
    qid = fetch_qaqc_id(conn, pid, qaqc_name)
    if legacy:
        pid = None
    qid = upsert_table_qaqc(conn, data, pid, qid)
    logger.debug(f"QAQC ID {qid}")

    n = delete_qaqc_tests(conn, qid)
    logger.debug(f"deleted {n} config tests")

    n = insert_qaqc_tests(conn, qid, tests, version=version)
    logger.debug(f"inserted {n} config tests")

    return qid
