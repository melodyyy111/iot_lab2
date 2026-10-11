
import os
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

load_dotenv()

url = os.getenv("INFLUX_URL")
org = os.getenv("INFLUX_ORG")
bucket = os.getenv("INFLUX_BUCKET")
token = os.getenv("INFLUX_TOKEN")

with InfluxDBClient(
    url=url,
    token=token,
    org=org
) as client:
    print("InfluxDB ping:", client.ping())

    buckets = client.buckets_api().find_buckets().buckets

    for item in buckets:
        print("Bucket:", item.name)

    print("Bucket cần dùng:", bucket)
