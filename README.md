# Get started with ZID/TSM

The orchestration repository is the place where all the little [ZID/TSM
components](https://git.ufz.de/rdm-software/timeseries-management) are
combined to a running system. This is achieved by putting the docker
images of the ZID/TSM components together in a
[docker compose file](docker-compose.yml) so you can start them with a
single command and without deeper knowledge of every single part of it.

Used [ZID/TSM
components](https://git.ufz.de/rdm-software/timeseries-management) in
that repo:

- [tsm-orchestration](https://git.ufz.de/rdm-software/timeseries-management/tsm-orchestration)
- [tsm-extractor](https://git.ufz.de/rdm-software/timeseries-management/tsm-extractor)
- [tsm-dispatcher](https://git.ufz.de/rdm-software/timeseries-management/tsm-dispatcher)
- [TSM Basic Demo Scheduler](https://git.ufz.de/rdm-software/timeseries-management/tsm-basic-demo-scheduler)

## 1. Create environment/config file from example:

```bash
cp .env.example .env 
```
The settings from the example are ok for local testing and development.
Postgres, Minio and MQTT services are exposed on localhost, so you can
access them with clients from your machine.

When using this in (semi-) production (e.g. on a server) some settings,
especially the passwords should be changed! Also keep in mind, that you
will need encryption when exposing the services: For example, minio HTTP
ports will need a TLS proxy (i.e. nginx) with certificates (i.e.
issued by
[DFN PKI](https://www.pki.dfn.de/geant-trusted-certificate-services/)).

### TSM-TEMP: Temporary Changes (Local FROST Views)

> **Note**: This codebase contains temporary changes marked with `TSM-TEMP-DISABLED` and `TSM-TEMP-FIX` comments. These changes disable SMS backend integration and use local database tables for FROST SensorThings views.

**What's changed:**
- FROST views query local `thing`/`datastream`/`observation` tables instead of `sms_*` tables
- DDL/DML deployment includes search_path fix for schema isolation
- Grafana views use simplified local queries

**To find all temporary changes:**
```bash
grep -r "TSM-TEMP" src/
```

**To revert to SMS-based views:**
1. Set `USE_LOCAL_STA_VIEWS=false` in `.env`
2. Rebuild workers: `docker-compose up -d --build worker-thing-setup`

##  2. Run all the services and have fun

- To start the services:
  - execute `./up.sh`
- To stop the services:
  - execute `./down.sh`
- To start the services including the `docker-compose-dev.yml` (see chapter "Extend or override docker-compose" for more information)
  - execute `./up-with-dev.sh` 
- To stop the services including the `docker-compose-dev.yml`
  - execute `./down-with-dev.sh`
- To execute any docker compose command use either
  -  `./dc.sh` <command>
  -  `./dc-with-dev.sh` <command>

It will take some seconds until everything is up.

## 3. Create a thing

A *thing* in ZID/TSM/STA sense is an entity that is producing time
series data in one or more data streams. In ZID/TSM we follow the
approach, that an end user is able to create a new *thing* and all its
settings for its infrastructure like database credentials or parser
properties. When somebody enters or changes settings of a *thing* these
changes are populated to *action services* by MQTT events.

### Option A: Using legacy event format

```bash
cat thing-event-msg.json | docker-compose exec -T mqtt-broker sh -c "mosquitto_pub -t thing_creation -u \$MQTT_USER -P \$MQTT_PASSWORD -s"
```

### Option B: Using frontend_thing_update (recommended)

Create a thing JSON file (e.g., `test-create-thing.json`) with the following structure:

```json
{
  "version": 7,
  "uuid": "11111111-1111-1111-1111-111111111111",
  "name": "MyMqttThing",
  "description": "MQTT-enabled thing for sensor data",
  "ingest_type": "mqtt",
  "mqtt_device_type": "chirpstack_generic",
  "project": {
    "name": "MyProject",
    "uuid": "22222222-2222-2222-2222-222222222222"
  },
  "database": {
    "schema": "my_project",
    "username": "my_project",
    "password": "<fernet_encrypted_password>",
    "ro_username": "ro_my_project",
    "ro_password": "<fernet_encrypted_password>",
    "url": "postgresql://my_project@database:5432/postgres",
    "ro_url": "postgresql://ro_my_project@database:5432/postgres"
  },
  "mqtt": {
    "username": "u_my_mqtt_thing",
    "password": "<fernet_encrypted_password>",
    "password_hash": "<pbkdf2_hash>",
    "topic": "mqtt_ingest/u_my_mqtt_thing/data"
  },
  "parsers": {"default": 0, "parsers": [{"type": "csvparser", "name": "MyParser", "settings": {}}]},
  "raw_data_storage": {"bucket_name": "my-thing-bucket", "username": "u_my_bucket", "password": "<fernet_encrypted_password>", "filename_pattern": "*"},
  "external_sftp": {},
  "external_api": {}
}
```

Publish the thing creation message:

```bash
cat test-create-thing.json | docker-compose exec -T mqtt-broker mosquitto_pub -h localhost -p 1883 -u mqtt -P mqtt -t frontend_thing_update -s -q 2
```

### Encrypting passwords with Fernet

Passwords must be encrypted using the Fernet key from `.env`:

```bash
python3 -c "
from cryptography.fernet import Fernet
key = 'CKoB---DEFAULT-DUMMY-SECRET---0exKVH0QDLy1B='  # FERNET_ENCRYPTION_SECRET
f = Fernet(key)
print(f.encrypt(b'your_password_here').decode())
"
```

## 3.1. Publish MQTT sensor data

Once a thing with MQTT ingestion is created, publish data to its topic:

```bash
# For chirpstack_generic parser format:
echo '{"time": "2026-01-30T12:00:00Z", "object": {"temperature": 23.5, "humidity": 65.2}}' | \
  docker-compose exec -T mqtt-broker mosquitto_pub -h localhost -p 1883 -u mqtt -P mqtt \
  -t "mqtt_ingest/u_my_mqtt_thing/data" -s -q 2
```

## 3.2. Create a thing for file ingestion

For things that ingest data from files (CSV, etc.) uploaded to MinIO:

```json
{
  "version": 7,
  "uuid": "33333333-3333-3333-3333-333333333333",
  "name": "MyFileThing",
  "description": "Thing for CSV file ingestion",
  "ingest_type": "file",
  "project": {
    "name": "MyFileProject",
    "uuid": "44444444-4444-4444-4444-444444444444"
  },
  "database": {
    "schema": "my_file_project",
    "username": "my_file_project",
    "password": "<fernet_encrypted_password>",
    "ro_username": "ro_my_file_project",
    "ro_password": "<fernet_encrypted_password>",
    "url": "postgresql://my_file_project@database:5432/postgres",
    "ro_url": "postgresql://ro_my_file_project@database:5432/postgres"
  },
  "parsers": {
    "default": 0,
    "parsers": [{
      "type": "csvparser",
      "name": "MyCsvParser",
      "settings": {
        "delimiter": ",",
        "date_format": "%Y-%m-%d %H:%M:%S",
        "date_position": "TimeField",
        "skip_rows": 1
      }
    }]
  },
  "raw_data_storage": {
    "bucket_name": "my-file-thing-bucket",
    "username": "u_my_file_bucket",
    "password": "<fernet_encrypted_password>",
    "filename_pattern": "*.csv"
  },
  "external_sftp": {},
  "external_api": {}
}
```

Upload files to the MinIO bucket at: http://localhost:9001/buckets/my-file-thing-bucket/browse

### 3.3. Understanding the Parser Body

The `parsers` section (stored in [test-parser-config.json](file:///home/siki/dpV2/tsm-orchestration/test-parser-config.json)) defines how the raw data should be interpreted.

For the `csvparser`, the `settings` object must include:
- `delimiter`: The character separating values (e.g., `,` or `;`).
- `header`: The 0-based index of the row containing column names (usually `0`).
- `timestamp_columns`: An **array of objects** specifying which columns form the timestamp.
  - `column`: The 0-based index of the column.
  - `format`: The date/time format using standard `strptime` syntax (e.g., `%Y-%m-%d %H:%M:%S`).

> [!NOTE]
> If your timestamp is split across multiple columns (e.g., Date in col 0 and Time in col 1), you can provide multiple objects in the `timestamp_columns` array. They will be concatenated with a space before parsing.

### 3.4. Unit Metadata for Datastreams (FROST)

The FROST SensorThings API exposes `UNIT_OF_MEASUREMENT` for each datastream with three fields:
- `name`: Human-readable unit name (e.g., "Celsius")
- `symbol`: Unit symbol (e.g., "°C")
- `definition`: URI reference to unit definition (e.g., "http://qudt.org/vocab/unit/DEG_C")

#### Current Behavior

With local views (`USE_LOCAL_STA_VIEWS=true`), unit metadata is extracted from the `datastream.properties` JSON field. If not set, the datastream `position` (column name) is used as the unit name.

#### How to Populate Unit Metadata

**Option 1: Update datastream properties after creation**

After data ingestion creates the datastreams, update their properties:

```bash
docker-compose exec -T -e PGPASSWORD=postgres database psql -U postgres -d postgres -c "
UPDATE my_schema.datastream 
SET properties = jsonb_build_object(
    'unit_name', 'Celsius',
    'unit_symbol', '°C',
    'unit_definition', 'http://qudt.org/vocab/unit/DEG_C'
)
WHERE position = 'temperature';
"
```

**Option 2: Batch update all datastreams**

```sql
-- Example: Set units based on column/position name patterns
UPDATE datastream SET properties = 
    CASE 
        WHEN position ILIKE '%temp%' THEN '{"unit_name": "Celsius", "unit_symbol": "°C", "unit_definition": "http://qudt.org/vocab/unit/DEG_C"}'::jsonb
        WHEN position ILIKE '%humid%' THEN '{"unit_name": "Percent", "unit_symbol": "%", "unit_definition": "http://qudt.org/vocab/unit/PERCENT"}'::jsonb
        WHEN position ILIKE '%press%' THEN '{"unit_name": "Hectopascal", "unit_symbol": "hPa", "unit_definition": "http://qudt.org/vocab/unit/HectoPA"}'::jsonb
        ELSE properties
    END;
```

#### Future Enhancements

> [!TIP]
> To fully automate unit metadata:
> 1. Extend the thing creation payload to include a `datastream_units` mapping
> 2. Modify `timeio-db-api` to set `datastream.properties` when creating datastreams
> 3. Or create a post-processing worker that sets units based on naming conventions

The dispatcher action services will create
- a new minio user and bucket:
  - <http://localhost:9001/buckets/thedoors-057d8bba-40b3-11ec-a337-125e5a40a849/admin/summary>
  - <http://localhost:9001/buckets/thedoors-057d8bba-40b3-11ec-a337-125e5a40a849/browse>
- a new postgres database role and schema:
  - <postgresql://myfirstproject_6185a5b8462711ec910a125e5a40a845:d0ZZ9d3QSDZ6tXIZTnKRY1uVLKIc05GmQh8SA36M@postgres/postgres>
  -   and a *thing* entity with (hopefully) all the necessary properties
      in the new `thing` table


## 4. Upload data

### Option A: Using MinIO Web Console
Go to the fresh new bucket in the [MinIO console](http://localhost:9001) and upload a CSV file.

### Option B: Using MinIO mc CLI (API)

You can upload files programmatically using the MinIO `mc` CLI via Docker:

```bash
# Create and upload a test CSV file
cat > test-data.csv << 'EOF'
timestamp,temperature,humidity,pressure
2026-01-30 12:00:00,22.5,65.3,1013.2
2026-01-30 12:10:00,22.8,64.9,1013.1
EOF

# Upload to bucket using mc CLI
docker run --rm --network=tsm-orchestration_default \
  -v $(pwd)/test-data.csv:/test-data.csv \
  --entrypoint sh minio/mc -c \
  "mc alias set local http://object-storage:9000 minioadmin minioadmin && \
   mc cp /test-data.csv local/my-bucket-name/test-data.csv"

# List bucket contents
docker run --rm --network=tsm-orchestration_default \
  --entrypoint sh minio/mc -c \
  "mc alias set local http://object-storage:9000 minioadmin minioadmin && \
   mc ls local/my-bucket-name/"
```

**Note**: Replace `my-bucket-name` with your thing's bucket name. The file-ingest worker will automatically detect the upload and process the file.

The dispatcher action service called *run-process-new-file-service* gets
notified by a MQTT event produced by minio and will forward the file
resource and the necessary settings to the scheduler. The scheduler
starts the extractor wo will parse the data and write it to the things
database.

## 5. Clean up

To temporary stop the containers and services use `docker-compose stop`.

When you're ready or destroyed your setup while playing around you can
reset everything by kicking away the containers and removing all data:

```bash
docker-compose down --timeout 0 -v --remove-orphans && ./remove-all-data.sh
```

All data is lost with this. Be careful!

# Using SFTP and FTP for uploads 

The minio object storage provides SFTP and FTP services. Its automatically equipped with self signed TLS certs for FTP
and a generated SSH host key. Please change the TLs certificates to some officially signed, you can take the same certs
that are used by the proxy.

You can directly use the minio accounts, but it would be better to use minio service accounts for authentication.

## Testing FTP service with `lftp`

With the [previously generated account](#3-create-a-thing) and the default settings:

```bash
lftp -p 40021 thedoors-057d8bba-40b3-11ec-a337-125e5a40a849@localhost -e "set ssl:ca-file ./data/minio/certs/minio-ftp.crt"
```

In development mode with self signed certificate we have to define the CA. 

## Testing SFTP service with `sftp`

With the [previously generated account](#3-create-a-thing) and the default settings:

```bash
sftp -P 40022 thedoors-057d8bba-40b3-11ec-a337-125e5a40a849@localhost
```

# Further thoughts and hints

## Configuring and operating Mosquitto MQTT broker

## General

When using in production it is recommended to use the `mosquitto.tls.conf` template (change
`MOSQUITTO_CONFIG` in your `.env` file) to enable encrypted connections by tls.

When started the first time it generates a password database
(`data/mosquitto/passwd/mosquitto.passwd`) with the credentials from the environment. Later 
changes of the password and user in env do not have any effect to the password file but will
break the health check of the service. To change passwords or add users use the 
`mosquitto_passwd` command from inside the container:

```bash
docker-compose run --rm mqtt-broker mosquitto_passwd -b /tmp/mosquitto/auth/mosquitto.passwd "user" "password"
```

With interactive password input:

```bash
docker-compose run --rm mqtt-broker mosquitto_passwd /tmp/mosquitto/auth/mosquitto.passwd "user"
```

### Example for adding a new user and an acl to publish data

1. Start the mqtt-broker service with `docker-compose up mqtt-broker` at least once the create 
   the initial `mosquitto.passwd` and `mosquitto.acl` files.
2. Call ``docker-compose exec mqtt-broker bash -c $'echo `echo -n "MY_NEW_MQTT_USER:" && /mosquitto/pw -p "MY_NEW_MQTT_PASSWORD"` >> /tmp/mosquitto/auth/mosquitto.passwd'``
   to add the new user with its password 
3. Restart the mqtt-broker service `docker-compose restart mqtt-broker`
4. From now on you should be able to publish to the new users topic namespace:
   ```bash
   echo "very nice data!" | docker-compose exec -T mqtt-broker sh -c "mosquitto_pub -t mqtt_ingest/MY_NEW_MQTT_USER/beautiful/sensor/1 -u MY_NEW_MQTT_USER -P MY_NEW_MQTT_PASSWORD -s"
   ```
   Watch them by checking the output of the mqtt-cat service:
   `docker-compose logs --follow mqtt-cat`

### mosquitto_ctrl

[mosquitto_ctrl](https://mosquitto.org/man/mosquitto_ctrl-1.html) seems to be a new API to 
configure the mosquitto server on runtime without to reload it when things change.

### Mosquitto auth plugins

For dynamic acls from database: https://gist.github.com/TheAshwanik/7ed2a3032ca16841bcaa


## Minio

- Yes, we really need four volumes, otherwise object lock will not work.
- Find the current event ARN to configure bucket notifications:

    ```bash
    mc admin info  myminio/ --json | jq .info.sqsARN
    ```

## Naming conventions

Human readable ID for projects and things: Use UUID as suffix and
sanitized name to fill it from the left until it is 63 chars long.

```pathon
import re


def slug(self):
    return re.sub(
        '[^a-z0-9_]+',
        '',
        '{shortname}_{uuid}'.format(shortname=self.name[0:30].lower(), uuid=self.uuid)
    )
    
# Or with minus chars at all but less space for the name
    def slug_with_minus(self):
        return re.sub(
            '[^a-z0-9\-]+',
            '',
            '{shortname}-{uuid}'.format(shortname=self.name[0:26].lower(), uuid=self.uuid)
        )
```

# Enable TLS Security for Postgres database

For secure connections over the network you need transport security like
`https`. To achieve this you need certificates of a public key
infrastructure (PKI) like the
[DFN PKI](https://www.pki.dfn.de/geant-trusted-certificate-services/).

Once you have a private key and a public certificate you can enable
security by

- changing `POSTGRES_TLS_CERT_PATH` to the path of your certificate file
- changing `POSTGRES_TLS_KEY_PATH` to the path of your private key file
- uncommenting the line beginning with `POSTGRES_EXTRA_PARAMS`

in the `.env` file of your deployment.

Now you're able to access the minio service with `https`. The postgres
database will enforce encryption but you need to enable
[`full-verification`](https://stackoverflow.com/questions/14021998/using-psql-to-connect-to-postgresql-in-ssl-mode) mode in client to also check the identity of the
server.

# Extend or override docker-compose

- preparations:
  - copy `docker-compose-dev.example.yml` and rename it to `docker-compose-dev.yml`
  - add your changes to `docker-compose-dev.yml`
  - note: changes to `docker-compose-dev.yml` are not added to version control
- To run locally and override or extend the `docker-compose.yml` you can use the following command:  
  -  `docker compose -f docker-compose.yml -f docker-compose-dev.yml  up -d`

## Mount local repositories into services

If you use the workflow described above (without making changes to `docker-compose-dev.example.env`), it will mount the code of the other local TSM repositories into their respective services. If you now make changes to the code or check out another branch in a repository, it will directly be present inside the services defined in the `docker-compose-dev.example.yml`. This way you don't have to build an image every time you change something in the code.

Please note that this will only work if you have the other TSM respositories in the same parent directory as tsm-orchestration, as shown below.

``` 
TSM_DIRECTORY (can be any dir)
├── tsm-orchestration
├── tsm-dispatcher
├── tsm-frontend
├── tsm-basic-demo-scheduler
├── tsm-extractor
└── tsm-ufz-tsmdl
```

# Keycloak as identity provider in development environment

## Admin console

- http://localhost:8081/admin/master/console/#/demo/ 
  - or: http://keycloak:8081/admin/master/console/#/demo/ (if you updated /etc/hosts)
  - or: http://keycloak:KEYCLOAK_PORT/admin/master/console/#/demo/ || http://localhost:KEYCLOAK_PORT/admin/master/console/#/demo/ (if you changed the port to something other than 8081) 
- Credentials:
  - User: `admin`
  - Password: `admin`

See [here](./keycloak/README.md) for further information regarding configuration and setup.