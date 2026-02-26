#!/usr/bin/env python3
from __future__ import annotations

import logging
import threading
import urllib.request
from functools import partial
from typing import Any, Callable

import psycopg
import requests
from psycopg import Connection, conninfo

from timeio.errors import DataNotFoundError


class Database:
    name = "database"

    def __init__(self, dsn: str):
        self.info = conninfo.conninfo_to_dict(dsn)
        self.info.pop("password")
        self.__dsn = dsn
        self.ping()

    @property
    def connection(self) -> Callable[[], psycopg.Connection]:
        return partial(psycopg.connect, self.__dsn)

    def ping(self, conn: Connection | None = None):
        try:
            if conn is not None:
                conn.execute("")
            else:
                with self.connection() as conn:
                    conn.execute("")
        except psycopg.errors.DatabaseError as e:
            raise ConnectionError(f"Ping to {self.name} failed. ({self.info})") from e


class DBapi:

    def __init__(self, base_url, auth_token):
        self.base_url = base_url
        self.auth_token = auth_token
        self.ping_dbapi()

    def ping_dbapi(self):
        """
        Test the health endpoint of the given url.

        Added in version 0.4.0
        """
        with urllib.request.urlopen(f"{self.base_url}/health") as resp:
            if not resp.status == 200:
                raise ConnectionError(
                    f"Failed to ping. HTTP status code: {resp.status}"
                )

    def upsert_observations(self, thing_uuid: str, observations: list[dict[str, Any]]):
        url = f"{self.base_url}/observations/upsert/{thing_uuid}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth_token}",
        }
        # Debug logging
        logging.info(f"POST to {url}")
        logging.info(f"Headers: Content-Type={headers['Content-Type']}, Authorization={headers['Authorization'][:15]}***")

        response = requests.post(
            url,
            json={"observations": observations},
            headers=headers,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"upload to {thing_uuid} failed with "
                f"{response.reason} and {response.text}"
            )
