from __future__ import annotations

import logging
import types
import inspect
from typing import Type

from minio import Minio
from minio.error import S3Error

from timeio.common import get_envvar
from timeio.parser.mqtt_parser import MqttParser

logger = logging.getLogger("dynamic-loader")


def _get_minio_client() -> Minio:
    return Minio(
        endpoint=get_envvar("MINIO_URL"),
        access_key=get_envvar("MINIO_ACCESS_KEY"),
        secret_key=get_envvar("MINIO_SECURE_KEY"),
        secure=get_envvar("MINIO_SECURE", default=True, cast_to=bool),
    )


def load_dynamic_parser(bucket_name: str, object_name: str) -> Type[MqttParser]:
    """
    Fetch a Python script from MinIO, execute it, and return the MqttParser class defined in it.
    """
    client = _get_minio_client()
    try:
        response = client.get_object(bucket_name, object_name)
        code = response.read().decode("utf-8")
    except S3Error as e:
        logger.error(f"Failed to fetch parser script {bucket_name}/{object_name}: {e}")
        raise ImportError(f"Could not fetch parser script: {e}")
    finally:
        if 'response' in locals():
            response.close()
            
    # Create a new module
    module_name = f"dynamic_parser_{object_name.replace('.', '_')}"
    module = types.ModuleType(module_name)
    
    # Execute the code in the module's namespace
    try:
        exec(code, module.__dict__)
    except Exception as e:
        logger.error(f"Failed to execute dynamic parser script {object_name}: {e}")
        raise ImportError(f"Syntax error or runtime error in parser script: {e}")

    # Find the MqttParser subclass
    parser_class = None
    for name, obj in module.__dict__.items():
        if (
            isinstance(obj, type)
            and issubclass(obj, MqttParser)
            and obj is not MqttParser
        ):
            parser_class = obj
            break
            
    if not parser_class:
        raise ImportError(f"No subclass of MqttParser found in {object_name}")

    logger.info(f"Successfully loaded dynamic parser class {parser_class.__name__} from {object_name}")
    return parser_class
