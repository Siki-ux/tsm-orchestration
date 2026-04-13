#!/usr/bin/env python3
from __future__ import annotations

import io
import logging

from paramiko import WarningPolicy
from timeio.mqtt import AbstractHandler, MQTTMessage
from timeio.common import get_envvar, setup_logging
from timeio.crypto import decrypt, get_crypt_key
from timeio.remote_fs import MinioFS, FtpFS, sync
from timeio.feta import Thing
from timeio.typehints import MqttPayload
from timeio.journaling import Journal

logger = logging.getLogger("sync-ext-sftp")
journal = Journal("sync_ext_sftp")

USAGE = """
Usage: sftp_sync.py THING_UUID
Sync external SFTP files to minio storage.

Arguments
  THING_UUID        UUID of the thing.

Additional set the following environment variables:

  MINIO_URL         Minio URL to sync to.
  MINIO_USER        Minio user with r/w privileges
  MINIO_PASSWORD    Password for minio user above.
  MINIO_SECURE      Use minio secure connection; [true, false, 1, 0]
  CONFIGDB_DSN      DB which stores the credentials for the external sftp server
                    (source of sync) and also the (existing) bucket-name for the
                    target S3 storage. See also DSN format below.

  LOG_LEVEL         Set the verbosity, defaults to INFO.
                    [DEBUG, INFO, WARNING, ERROR, CRITICAL]
  FERNET_ENCRYPTION_SECRET  Secret used to decrypt sensitive information from
                    the Config-DB.

DSN format:
  postgresql://[user[:password]@][netloc][:port][/dbname]
"""


class SyncExtSftpManager(AbstractHandler):

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

    def act(self, content: MqttPayload.SyncExtSftpT, message: MQTTMessage):
        thing = Thing.from_uuid(content["thing"], dsn=self.configdb_dsn)
        minio_secure = get_envvar("MINIO_SECURE").lower() not in ["false", "0"]
        target = MinioFS.from_credentials(
            endpoint=get_envvar("MINIO_URL"),
            access_key=get_envvar("MINIO_USER"),
            secret_key=get_envvar("MINIO_PASSWORD"),
            bucket_name=thing.s3_store.bucket,
            secure=minio_secure,
        )
        priv_key = decrypt(thing.ext_sftp.ssh_priv_key, get_crypt_key()) if thing.ext_sftp.ssh_priv_key else ""
        password = decrypt(thing.ext_sftp.password, get_crypt_key()) if thing.ext_sftp.password else ""
        try:
            source = FtpFS.from_credentials(
                uri=thing.ext_sftp.uri,
                username=thing.ext_sftp.user,
                password=password,
                path=thing.ext_sftp.path,
                keyfile_path=io.StringIO(priv_key),
                missing_host_key_policy=WarningPolicy(),
            )
        except Exception as e:
            msg = f"Failed to create SFTP client. Reason: {e}"
            journal.error(msg, thing.uuid)
            logger.error(msg)
            return
        sync(source, target, thing.uuid)
        source.close()


if __name__ == "__main__":
    setup_logging(get_envvar("LOG_LEVEL", "INFO"))
    SyncExtSftpManager().run_loop()
