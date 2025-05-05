# NoSQLBench YAML Generator (Simplified Version)

A web application for Cassandra specialists and DataStax engineers to generate NoSQLBench YAML files from CQL schemas.

This simplified version works without the Cassandra driver dependency, making it easier to run on any system.

## Features

- Convert Cassandra CQL schemas to NoSQLBench YAML files
- Generate data binding configurations automatically 
- Simulate database connections
- Simulate NoSQLBench execution
- Download generated YAML files individually or as a ZIP archive

## Quick Start

1. Install the Python dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the application:
   ```
   python app.py
   ```

3. Access the web interface at http://localhost:5000

## Running with Docker

1. Build the Docker image:
   ```
   docker build -t nosqlbench-yaml-generator-simple -f Dockerfile .
   ```

2. Run the container:
   ```
   docker run -p 5000:5000 nosqlbench-yaml-generator-simple
   ```

3. Access the web interface at http://localhost:5000

## API Usage

The application provides the following API endpoints:

### Parse CQL Schema

```
POST /api/parse-cql
Content-Type: application/json

{
  "schema": "CREATE TABLE my_keyspace.my_table (id text PRIMARY KEY, value text);"
}
```

### Generate YAML Files

```
POST /api/generate-yaml
Content-Type: application/json

{
  "keyspace": "my_keyspace",
  "schema": "CREATE TABLE my_table (id text PRIMARY KEY, value text);",
  "cycles": 10000000,
  "threads": "auto"
}
```

### Download a YAML File

```
GET /api/download-yaml?id=file_id
```

### Download All YAML Files as ZIP

```
GET /api/download-all
```

### Simulate Database Connection

```
POST /api/connect
Content-Type: application/json

{
  "type": "cassandra",
  "hosts": "127.0.0.1",
  "port": 9042,
  "datacenter": "datacenter1",
  "username": "cassandra",
  "password": "cassandra"
}
```

### Simulate Running NoSQLBench

```
POST /api/run-nosqlbench
Content-Type: application/json

{
  "yaml_id": "file_id",
  "connection_id": "conn_id",
  "keyspace": "my_keyspace",
  "options": "write_cl=LOCAL_ONE threads=16"
}
```

## Example CQL Schema

Here's an example CQL schema you can use for testing:

```sql
CREATE TABLE centralpayment.pay_with_app_purchase_request_by_id (
    sessionid text,
    insertedtimestamp timestamp,
    amount decimal,
    fraudcheckisrequested boolean,
    fsaamount decimal,
    fsarxamount decimal,
    giftcardeligibleamount decimal,
    lanenumber text,
    ordertotal decimal,
    salestaxamount decimal,
    storenumber text,
    transactiondate timestamp,
    PRIMARY KEY (sessionid, insertedtimestamp)
) WITH CLUSTERING ORDER BY (insertedtimestamp DESC);

CREATE TABLE centralpayment.transaction_by_id (
    transactionid text,
    amount decimal,
    cardtype text,
    processeddate timestamp,
    status text,
    storenumber text,
    PRIMARY KEY (transactionid)
);
```

## Troubleshooting

If you encounter any issues with the Cassandra driver dependencies:

1. Make sure you're using the simplified version (app.py) which doesn't require the Cassandra driver
2. Check the Python version (3.6+ recommended)
3. If you need real database connec