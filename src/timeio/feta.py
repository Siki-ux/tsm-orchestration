from __future__ import annotations

import atexit
import warnings
from typing import Any, TypedDict

from timeio.errors import DataNotFoundError

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

import psycopg
from psycopg import Connection, sql
from psycopg.rows import dict_row
import logging
from timeio.typehints import JsonObjectT

logger = logging.getLogger("feta")

"""
FETA - Front End Thing Abstraction 

This file provide a convenient way to access the (meta-) data 
from the frontend (Thing, Project, QC-Settings, etc.) Currently 
this is a simple wrapper around the configDB, but also a (nearly 
complete[1]) drop-in replacement for classes in thing.py. 

[1]
- `thing.ExternalSFTP.private_key_path` is not supported, 
    because now we store the private ssh key directly in 
    the DB. One should use `feta.ExtSFTP.ssh_priv_key` 
    instead.
- `thing.Thing.properties` is not supported, because we 
    don't use/need it anymore. 
"""


class QcStreamT(TypedDict):
    arg_name: str
    sta_thing_id: int | None
    sta_stream_id: int | None
    alias: str


class ObjectNotFound(Exception):
    pass


def _prop(f):
    # this is a simple wrapper that allow the typehints from
    # the class to be recognized
    return property(f)


def _fetch(query, id_attr: str, column: str):
    """
    Return a property, with a getter that returns a single value (str, int, float, etc.)

    :param id_attr: The attr on the `cls` to put in the query
    :param column: key to unpack the result from dict-row where the
                   keys are the columns of the table.
    """

    def fetch(self: Base) -> None | Base:
        id_value = getattr(self, id_attr)
        if id_value is None:
            return None
        # use the query, which fetch a value for cacheing, because
        # we don't have an instance of feta.Base as result.
        key = (query, id_value)
        if cached := self._cache_get(key):
            return cached
        res = self._fetchall(self._conn, query, id_value)
        if not res:
            return None
        if len(res) > 1:
            warnings.warn(
                f"Got multiple results from {query} with {id_attr}={id_value}"
                f"Using the first result only.\n"
                f"First 5 results: {res[:5]}",
                UserWarning,
                stacklevel=2,
            )
        try:
            return res[0][column]
        except KeyError as e:
            e.add_note(
                f"Key not found in result {res[0]!r} of "
                f"query {query!r} with {id_attr}={id_value}"
            )
            raise e

    return property(fetch)


def _create(cls: type[Base], query: str, id_attr: str):
    """
    Return a property, with a getter that returns another Model

    :param query: The query to execute on request of the property
    :param id_attr: The attr on the `cls` to put in the query
    :param cls: The final class to create from the result of the query
    """

    def fetch(self: Base) -> None | Base:
        id_value = getattr(self, id_attr)
        if id_value is None:
            return None
        key = (cls, id_value)
        if cached := self._cache_get(key):
            return cached
        res = self._fetchall(self._conn, query, id_value)
        if not res:
            raise ObjectNotFound(
                f"Could not create {cls.__qualname__}"
                f"(table={cls._schema}.{cls._table_name}) "
                f"with {id_attr}={id_value} from {self}"
            )
        if len(res) > 1:
            warnings.warn(
                f"Got multiple results from {cls._schema}.{cls._table_name} "
                f"with {id_attr}={id_value}. Creating {cls.__qualname__} "
                f"from the first result only.",
                UserWarning,
                stacklevel=2,
            )
        inst = cls._from_parent(res[0], self)
        self._cache_set(key, inst)
        return inst

    return property(fetch)


def connect(dsn: str, **kwargs):
    """
    Globally connect feta with a DB.

    The connection will be valid for the whole python session.
    To create just a temporary connection, one can pass the dsn
    argument to the different constructors.
    For example `Thing.from_id(1, dsn=...)`

    :param dsn: connection string
    :param kwargs: kwargs are directly passed to psycopg.connect()
    """
    Base._set_global_connection(dsn, **kwargs)


class Base:
    __cls_connection: Connection | None = None
    _table_name: str = "<not set>"
    _schema: str = "<not set>"
    _protected_values = frozenset()

    def __init__(self, attrs, conn: Connection, caching: bool):
        """Constructor for creating a new Base instance from scratch.

        See also Base._from_parent(), which create a new instance
        from and existing Base instance, in other words, from within
        an instance-method you should call _from_parent.
        """
        self._attrs = attrs
        self._conn = conn
        self._cache = {} if caching else None
        self._root = True

    @classmethod
    def _from_parent(cls, res, parent: Base) -> Base:
        """Constructor for creating an instance from an existing Base instance.

        For creating a new instance from scratch, in other words,
        from within a classmethod call __init__, but from within
        an instance-method call this.
        """
        # Only the root class
        instance = cls(res, parent._conn, False)
        instance._cache = parent._cache
        instance._root = False
        return instance

    def __repr__(self):
        attrs = self._attrs.copy()
        attrs.update({k: "*****" for k in self._protected_values})
        return f"{self.__class__.__name__}({str(attrs)[1:-1]})"

    def __del__(self):
        if self._root:
            # The class connection is registered with atexit
            # and will be closed on program exit.
            if self._conn == self.__cls_connection:
                return
            # On connection creation we set the owner attribute
            # mark the connection as ours (see Base._get_connection).
            if getattr(self._conn, "owner", None) == "feta":
                logger.debug(f"Closing instance connection {self._conn}")
                self._conn.close()

    @classmethod
    def _set_global_connection(cls, dsn, **kwargs):
        """See also feta.connect"""
        cls.__cls_connection = conn = psycopg.connect(dsn, **kwargs)
        logger.debug(f"Opened global DB connection {conn}")

        def close_global_connection():
            conn.close()
            logger.debug(f"Closed global DB connection {conn}")

        atexit.register(close_global_connection)

    @classmethod
    def _get_connection(
        cls, dsn: str | Connection | None = None, **kwargs
    ) -> Connection:
        # The user passed a connection or a dsn
        if dsn is not None:
            if isinstance(dsn, Connection):
                return dsn
            conn = psycopg.connect(dsn, **kwargs)
            logger.debug(f"Opened instance connection {conn}")
            # We mark the connection as ours, to differentiate it
            # from a user given connection. On __del__ we just want
            # to close a connections if it is under our care.
            conn.owner = "feta"
            return conn
        # Check for an existing class connection
        if cls.__cls_connection is not None:
            return cls.__cls_connection
        raise ValueError(
            f"Either pass the keyword argument 'dsn', or use the "
            f"function feta.connect() to set a global connection "
            f"for all FETA classes."
        )

    @staticmethod
    def _fetchall(conn: Connection, query, *params) -> list[dict[str, Any]]:
        logger.debug("fetchall(%s, %s)", query, params)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return cur.fetchall()  # type: ignore

    @staticmethod
    def _fetchone(conn: Connection, query, *params):
        logger.debug("fetchone(%s, %s)", query, params)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def _cache_get(self, key):
        if self._cache:
            hit = key in self._cache
            logging.getLogger("feta-cache").debug(
                "cache %s: %s", "HIT" if hit else "MISS", key
            )
            return self._cache.get(key, None)
        return None

    def _cache_set(self, key, value):
        if self._cache is not None:
            self._cache[key] = value

    def clear_cache(self):
        if self._cache:
            self._cache.clear()

    def to_dict(self) -> dict[str, Any]:
        return self._attrs.copy()

    # Each table has a PK column, that is named 'id'. That
    # is why we can safely add this to EVERY subclass.
    @classmethod
    def from_id(
        cls: type[Self],
        id_: int,
        dsn: str | Connection | None = None,
        caching: bool = True,
        **kwargs,
    ) -> Self:
        """
        Fetch a new object by its ID.

        :param id_: The id of the object.
        :param dsn: Postgres connection or connection string to make a DB
            connection with `psycopg.connect()`
        :param caching: If `True` (default) the object is cached and
            subsequently lookups will use the cached object. If `False`,
            the object is always fetched from its source (DB table).
        :param kwargs: All kwargs are passed on to the function `psycopg.connection`.
        :return: Returns an instance of a subclass of `feta.Base`
        """
        tab = sql.Identifier(cls._schema, cls._table_name)
        query = sql.SQL("select * from {tab} where id = %s").format(tab=tab)
        conn = cls._get_connection(dsn, **kwargs)
        if not (res := cls._fetchall(conn, query, id_)):
            raise ObjectNotFound(f"No {cls.__name__} found for id={id_}")
        if len(res) > 1:
            warnings.warn(
                f"Got multiple results from {cls._schema}.{cls._table_name} "
                f"for id={id_}. The returned object will be created from "
                f"the first result."
            )
        return cls(res[0], conn, caching)


class FromNameMixin:
    @classmethod
    def from_name(
        cls: type[Self],
        name: str,
        dsn: str | Connection | None = None,
        caching: bool = True,
        **kwargs,
    ) -> Self:
        """
        Create a new object from its name.

        :param name: The name of the object.
        :param dsn: Postgres connection or connection string to make a DB
            connection with `psycopg.connect()`
        :param caching: If `True` (default) the object is cached and
            subsequently lookups will use the cached object. If `False`,
            the object is always fetched from its source (DB table).
        :param kwargs: All kwargs are passed on to the function `psycopg.connection`.
        :return: Returns an instance of a subclass of `feta.Base`
        """
        tab = sql.Identifier(cls._schema, cls._table_name)
        query = sql.SQL("select * from {tab} where name = %s").format(tab=tab)
        conn = cls._get_connection(dsn, **kwargs)
        if not (res := cls._fetchall(conn, query, name)):
            raise ObjectNotFound(f"No {cls.__name__} found with {name=}")
        if len(res) > 1:
            warnings.warn(
                f"Got multiple results from {cls._schema}.{cls._table_name} "
                f"for {name=}. The returned object will be created from "
                f"the first result."
            )
        return cls(res[0], conn, caching)


class FromUUIDMixin:
    @classmethod
    def from_uuid(
        cls: type[Self],
        uuid: str,
        dsn: str | Connection | None = None,
        caching: bool = True,
        **kwargs,
    ) -> Self:
        """
        Create a new object by its UUID.

        :param uuid: The UUID of the object.
        :param dsn: Postgres connection or connection string to make a DB
            connection with `psycopg.connect()`
        :param caching: If `True` (default) the object is cached and
            subsequently lookups will use the cached object. If `False`,
            the object is always fetched from its source (DB table).
        :param kwargs: All kwargs are passed on to the function `psycopg.connection`.
        :return: Returns an instance of a subclass of `feta.Base`
        """
        uuid = str(uuid)  # prevent UUID object
        tab = sql.Identifier(cls._schema, cls._table_name)
        query = sql.SQL("select * from {tab} where uuid::text = %s").format(tab=tab)
        conn = cls._get_connection(dsn, **kwargs)
        if not (res := cls._fetchall(conn, query, uuid)):
            raise ObjectNotFound(f"No {cls.__name__} found for {uuid=}")
        if len(res) > 1:
            warnings.warn(
                f"Got multiple results from {cls._schema}.{cls._table_name} "
                f"for {uuid=}. The returned object will be created from "
                f"the first result."
            )
        return cls(res[0], conn, caching)


class IngestType(Base, FromNameMixin):
    _schema = "config_db"
    _table_name = "ingest_type"
    id: int = _prop(lambda self: self._attrs["id"])
    name: str = _prop(lambda self: self._attrs["name"])


class FileParserType(Base, FromNameMixin):
    _schema = "config_db"
    _table_name = "file_parser_type"
    id: int = _prop(lambda self: self._attrs["id"])
    name: str = _prop(lambda self: self._attrs["name"])


class MQTTDeviceType(Base, FromNameMixin):
    _schema = "config_db"
    _table_name = "mqtt_device_type"
    id: int = _prop(lambda self: self._attrs["id"])
    name: str = _prop(lambda self: self._attrs["name"])
    properties: JsonObjectT | None = _prop(lambda self: self._attrs.get("properties"))


class ExtAPIType(Base, FromNameMixin):
    _schema = "config_db"
    _table_name = "ext_api_type"
    id: int = _prop(lambda self: self._attrs["id"])
    name: str = _prop(lambda self: self._attrs["name"])


class Database(Base):
    _schema = "config_db"
    _table_name = "database"
    _protected_values = frozenset({"password", "ro_password"})
    id: int = _prop(lambda self: self._attrs["id"])
    schema: str = _prop(lambda self: self._attrs["schema"])
    user: str = _prop(lambda self: self._attrs["user"])
    password: str = _prop(lambda self: self._attrs["password"])
    ro_user: str = _prop(lambda self: self._attrs["ro_user"])
    ro_password: str = _prop(lambda self: self._attrs["ro_password"])
    url: str | None = _prop(lambda self: self._attrs["url"])
    ro_url: str | None = _prop(lambda self: self._attrs["ro_url"])

    # thing.Datebase interface
    # password url, ro_password, ro_url
    # are already defined above
    username = user
    ro_username = ro_user


class Project(Base, FromNameMixin, FromUUIDMixin):
    _schema = "config_db"
    _table_name = "project"
    id: int = _prop(lambda self: self._attrs["id"])
    name: str = _prop(lambda self: self._attrs["name"])
    uuid: str = _prop(lambda self: str(self._attrs["uuid"]))
    database_id: int = _prop(lambda self: self._attrs["database_id"])
    database: Database = _create(
        Database, f"SELECT * FROM {_schema}.database WHERE id = %s", "database_id"
    )

    # thing.Project interface
    # uuid and name are already defines above

    def get_things(self) -> list[Thing]:
        query = f"select * from {self._schema}.thing where project_id = %s"
        conn = self._conn
        return [
            Thing._from_parent(attr, self)
            for attr in self._fetchall(conn, query, self.id)
        ]

    def get_default_qaqc(self) -> QAQC | None:
        query = (
            f"select * from {self._schema}.qaqc q "
            f"where q.project_id = %s and q.default = true "
            f"order by q.id desc"
        )
        if res := self._fetchone(self._conn, query, self.id):
            return QAQC._from_parent(res, self)
        return None

    def get_qaqcs(self, id: int | None = None, name: str | None = None) -> list[QAQC]:
        params = [self.id]
        query = f"select * from {self._schema}.qaqc where project_id = %s "
        if id is not None:
            query += "and id = %s "
            params += [id]
        if name is not None:
            query += "and name = %s "
            params += [name]
        return [
            QAQC._from_parent(attr, self)
            for attr in self._fetchall(self._conn, query, *params)
        ]


class ExtAPI(Base):
    _schema = "config_db"
    _table_name = "ext_api"
    id: int = _prop(lambda self: self._attrs["id"])
    api_type_id: int = _prop(lambda self: self._attrs["api_type_id"])
    sync_interval: int = _prop(lambda self: self._attrs["sync_interval"])
    sync_enabled: bool = _prop(lambda self: self._attrs["sync_enabled"])
    settings: JsonT | None = _prop(lambda self: self._attrs["settings"])
    api_type: ExtAPIType = _create(
        ExtAPIType, f"SELECT * FROM {_schema}.ext_api_type WHERE id = %s", "api_type_id"
    )

    # thing.ExternalApi interface
    # sync_interval, settings
    # are already defined above
    enabled = sync_enabled
    api_type_name: str = _prop(lambda self: self.api_type.name)


class ExtSFTP(Base):
    _schema = "config_db"
    _table_name = "ext_sftp"
    _protected_values = frozenset({"password", "ssh_priv_key"})
    id: int = _prop(lambda self: self._attrs["id"])
    uri: str = _prop(lambda self: self._attrs["uri"])
    path: str = _prop(lambda self: self._attrs["path"])
    user: str = _prop(lambda self: self._attrs["user"])
    password: str | None = _prop(lambda self: self._attrs["password"])
    ssh_priv_key: str = _prop(lambda self: self._attrs["ssh_priv_key"])
    ssh_pub_key: str = _prop(lambda self: self._attrs["ssh_pub_key"])
    sync_interval: int = _prop(lambda self: self._attrs["sync_interval"])
    sync_enabled: bool = _prop(lambda self: self._attrs["sync_enabled"])

    # thing.ExternalSFTP interface
    # uri, path, password, sync_interval
    # are already defined above
    # Note that `private_key_path` from thing.py is not supported,
    # see also the module description.
    enabled = sync_enabled
    username = user
    public_key = ssh_pub_key


class FileParser(Base, FromUUIDMixin):
    _schema = "config_db"
    _table_name = "file_parser"
    id: int = _prop(lambda self: self._attrs["id"])
    file_parser_type_id: int = _prop(lambda self: self._attrs["file_parser_type_id"])
    name: str = _prop(lambda self: self._attrs["name"])
    uuid = _prop(lambda self: self._attrs["uuid"])
    params: JsonT | None = _prop(lambda self: self._attrs["params"])
    file_parser_type: FileParserType = _create(
        FileParserType,
        f"SELECT * FROM {_schema}.file_parser_type WHERE id = %s",
        "file_parser_type_id",
    )


class MQTT(Base):
    _schema = "config_db"
    _table_name = "mqtt"
    _protected_values = frozenset({"password", "password_hashed"})
    id: int = _prop(lambda self: self._attrs["id"])
    user = _prop(lambda self: self._attrs["user"])
    password = _prop(lambda self: self._attrs["password"])
    password_hashed = _prop(lambda self: self._attrs["password_hashed"])
    topic: str | None = _prop(lambda self: self._attrs["topic"])
    mqtt_device_type_id: int | None = _prop(
        lambda self: self._attrs["mqtt_device_type_id"]
    )
    mqtt_device_type: MQTTDeviceType | None = _create(
        MQTTDeviceType,
        f"SELECT * FROM {_schema}.mqtt_device_type WHERE id = %s",
        "mqtt_device_type_id",
    )


class QAQC(Base):
    _schema = "config_db"
    _table_name = "qaqc"
    id: int = _prop(lambda self: self._attrs["id"])
    name: str = _prop(lambda self: self._attrs["name"])
    project_id: int | None = _prop(lambda self: self._attrs["project_id"])
    context_window: str = _prop(lambda self: self._attrs["context_window"])
    project: Project | None = _create(
        Project, f"select * from {_schema}.project where id = %s", "project_id"
    )

    def get_tests(self) -> list[QAQCTest]:
        query = f"select * from {self._schema}.qaqc_test where qaqc_id = %s"
        conn = self._conn
        return [
            QAQCTest._from_parent(attr, self)
            for attr in self._fetchall(conn, query, self.id)
        ]


class QAQCTest(Base):
    _schema = "config_db"
    _table_name = "qaqc_test"
    id: int = _prop(lambda self: self._attrs["id"])
    qaqc_id: int = _prop(lambda self: self._attrs["qaqc_id"])
    function: str = _prop(lambda self: self._attrs["function"])
    args: JsonObjectT | None = _prop(lambda self: self._attrs["args"])
    position: int | None = _prop(lambda self: self._attrs["position"])
    name: str | None = _prop(lambda self: self._attrs["name"])
    streams: list[QcStreamT] | None = _prop(lambda self: self._attrs["streams"])
    qaqc: QAQC = _create(QAQC, f"select * from {_schema}.qaqc where id = %s", "qaqc_id")


class S3Store(Base):
    _schema = "config_db"
    _table_name = "s3_store"
    _protected_values = frozenset({"password"})
    id: int = _prop(lambda self: self._attrs["id"])
    user: str = _prop(lambda self: self._attrs["user"])
    password: str = _prop(lambda self: self._attrs["password"])
    bucket: str = _prop(lambda self: self._attrs["bucket"])
    filename_pattern: str | None = _prop(lambda self: self._attrs["filename_pattern"])
    file_parser_id: int = _prop(lambda self: self._attrs["file_parser_id"])
    file_parser: FileParser = _create(
        FileParser,
        f"select * from {_schema}.file_parser where id = %s",
        "file_parser_id",
    )

    # thing.RawDataStorage interface
    # password, filename_pattern
    # are already defined above
    username = user
    bucket_name = bucket


class Thing(Base, FromNameMixin, FromUUIDMixin):
    _schema = "config_db"
    _table_name = "thing"
    id: int = _prop(lambda self: self._attrs["id"])
    uuid = _prop(lambda self: str(self._attrs["uuid"]))
    name = _prop(lambda self: self._attrs["name"])
    project_id: int = _prop(lambda self: self._attrs["project_id"])
    ingest_type_id: int = _prop(lambda self: self._attrs["ingest_type_id"])
    s3_store_id: int | None = _prop(lambda self: self._attrs["s3_store_id"])
    mqtt_id: int = _prop(lambda self: self._attrs["mqtt_id"])
    ext_sftp_id: int | None = _prop(lambda self: self._attrs["ext_sftp_id"])
    ext_api_id: int | None = _prop(lambda self: self._attrs["ext_api_id"])
    description: str | None = _prop(lambda self: self._attrs["description"])
    project: Project = _create(Project, f"select * from {_schema}.project where id = %s", "project_id")  # fmt: skip
    ingest_type: IngestType = _create(IngestType, f"select * from {_schema}.ingest_type where id = %s", "ingest_type_id")  # fmt: skip
    s3_store: S3Store | None = _create(S3Store, f"select * from {_schema}.s3_store where id = %s", "s3_store_id")  # fmt: skip
    mqtt: MQTT = _create(MQTT, f"select * from {_schema}.mqtt where id = %s", "mqtt_id")  # fmt: skip
    ext_sftp: ExtSFTP | None = _create(ExtSFTP, f"select * from {_schema}.ext_sftp where id = %s", "ext_sftp_id")  # fmt: skip
    ext_api: ExtAPI | None = _create(ExtAPI, f"select * from {_schema}.ext_api where id = %s", "ext_api_id")  # fmt: skip
    legacy_qaqc_id: int | None = _prop(lambda self: self._attrs.get("legacy_qaqc_id"))

    # thing.Thing interface
    # uuid, name, project, description are already defined above
    database: Database = _prop(lambda self: self.project.database)
    raw_data_storage = s3_store
    external_sftp = ext_sftp
    external_api = ext_api
    # Note that thing.properties is not supported anymore
    properties = None

    def get_legacy_qaqc(self) -> QAQC | None:
        if self.legacy_qaqc_id is None:
            return None
        query = f"select * from {self._schema}.qaqc where id = %s"
        res = self._fetchone(self._conn, query, self.legacy_qaqc_id)
        return QAQC._from_parent(res, self)

    @classmethod
    def from_s3_bucket_name(
        cls: type[Self],
        bucket_name: str,
        dsn: str | Connection | None = None,
        caching: bool = True,
        **kwargs,
    ) -> Self:
        """
        Create a new Thing instance from an existing S3-bucket name.

        :param bucket_name: The S3 bucket_name.
        :param dsn: Postgres connection or connection string to make a DB
            connection with `psycopg.connect()`
        :param caching: If `True` (default) the object is cached and
            subsequently lookups will use the cached object. If `False`,
            the object is always fetched from its source (DB table).
        :param kwargs: All kwargs are passed on to the function
            `psycopg.connection`.
        :return: Returns a feta.Thing instance.
        """
        query = (
            f"select t.* from {cls._schema}.thing t join {cls._schema}.s3_store s3 on "
            "t.s3_store_id = s3.id where s3.bucket = %s"
        )
        conn = cls._get_connection(dsn, **kwargs)
        if not (res := cls._fetchall(conn, query, bucket_name)):
            raise ObjectNotFound(f"No {cls.__name__} found for {bucket_name=}")
        if len(res) > 1:
            warnings.warn(
                f"Got multiple results from {cls._schema}.thing for "
                f"{bucket_name=}. The returned Thing will be created "
                f"from the first result."
            )
        return cls(res[0], conn, caching)

    @classmethod
    def from_mqtt_user_name(
        cls: type[Self],
        mqtt_user_name: str,
        dsn: str | Connection | None = None,
        caching: bool = True,
        **kwargs,
    ) -> Self:
        """
        Create a new Thing instance from an existing mqtt username.

        :param mqtt_user_name: a MQTT username.
        :param dsn: Postgres connection or connection string to make a DB
            connection with `psycopg.connect()`
        :param caching: If `True` (default) the object is cached and
            subsequently lookups will use the cached object. If `False`,
            the object is always fetched from its source (DB table).
        :param kwargs: All kwargs are passed on to the function
            `psycopg.connection`.
        :return: Returns a feta.Thing instance.
        """
        query = (
            f"select t.* from {cls._schema}.thing t join mqtt m on "
            "t.mqtt_id = m.id where m.user = %s"
        )
        conn = cls._get_connection(dsn, **kwargs)
        if not (res := cls._fetchall(conn, query, mqtt_user_name)):
            raise ObjectNotFound(f"No {cls.__name__} found for {mqtt_user_name=}")
        if len(res) > 1:
            warnings.warn(
                f"Got multiple results from {cls._schema}.thing for "
                f"{mqtt_user_name=}. The returned Thing will be created "
                f"from the first result."
            )
        return cls(res[0], conn, caching)
