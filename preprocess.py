print("BAT DAU CHAY PREPROCESS")
import os
import numpy as np
import pandas as pd

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# 1. Doc cau hinh
load_dotenv()

URL = os.getenv("INFLUX_URL")
ORG = os.getenv("INFLUX_ORG")
BUCKET = os.getenv("INFLUX_BUCKET")
TOKEN = os.getenv("INFLUX_TOKEN")
DEVICE_ID = os.getenv("DEVICE_ID", "esp32_wokwi_01")

if not all([URL, ORG, BUCKET, TOKEN]):
    raise ValueError("Kiem tra file .env")

client = InfluxDBClient(
    url=URL,
    token=TOKEN,
    org=ORG
)

query_api = client.query_api()
write_api = client.write_api(
    write_options=SYNCHRONOUS
)

# 2. Doc du lieu tho trong 24 gio gan nhat
query = f'''
from(bucket: "{BUCKET}")
    |> range(start: -24h)
    |> filter(fn: (r) => r._measurement == "sensor_data")
    |> filter(fn: (r) => r.device_id == "{DEVICE_ID}")
    |> filter(fn: (r) =>
        r._field == "temperature" or
        r._field == "humidity" or
        r._field == "distance_cm"
    )
    |> pivot(
        rowKey: ["_time"],
        columnKey: ["_field"],
        valueColumn: "_value"
    )
    |> sort(columns: ["_time"])
'''

tables = query_api.query_data_frame(
    query=query,
    org=ORG
)

# InfluxDB co the tra ve mot DataFrame hoac danh sach DataFrame
if isinstance(tables, list):
    frames = [
        table for table in tables
        if isinstance(table, pd.DataFrame) and not table.empty
    ]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
else:
    df = tables

if df.empty:
    print("Chua co du lieu trong 24 gio gan nhat.")
    print("Hay kiem tra sensor_data va DEVICE_ID trong .env.")
    client.close()
    raise SystemExit

print("So dong du lieu tho:", len(df))

# 3. Chuan hoa du lieu
fields = ["temperature", "humidity", "distance_cm"]

for field in fields:
    if field not in df.columns:
        df[field] = np.nan
    df[field] = pd.to_numeric(
        df[field], errors="coerce"
    )

df["_time"] = pd.to_datetime(df["_time"], utc=True)
df = df.dropna(subset=["_time"])
df = df.sort_values("_time")
df = df.drop_duplicates(subset=["_time"], keep="last")
df = df.set_index("_time")

# 4. Xu ly gia tri ngoai le bang IQR
for field in fields:
    valid = df[field].dropna()

    if len(valid) >= 4:
        q1 = valid.quantile(0.25)
        q3 = valid.quantile(0.75)
        iqr = q3 - q1

        if iqr > 0:
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr

            mask = (
                (df[field] < lower) |
                (df[field] > upper)
            )
            count = int(mask.sum())

            if count > 0:
                print(
                    field,
                    "- so gia tri ngoai le:",
                    count
                )

            df.loc[mask, field] = np.nan

# 5. Lay mau moi 10 giay va tinh trung vi
processed = df[fields].resample("10s").median()

# 6. Xu ly gia tri thieu
processed[fields] = processed[fields].interpolate(
    method="time",
    limit=3,
    limit_area="inside"
)

# 7. Tinh trung binh truot, do thay doi va chuan hoa
for field in fields:
    processed[field + "_rolling_mean"] = (
        processed[field].rolling(
            window=3, min_periods=1
        ).mean()
    )

    processed[field + "_delta"] = (
        processed[field].diff()
    )

    min_value = processed[field].min()
    max_value = processed[field].max()

    if pd.notna(min_value) and pd.notna(max_value):
        if max_value > min_value:
            processed[field + "_norm"] = (
                (processed[field] - min_value) /
                (max_value - min_value)
            )
        else:
            processed[field + "_norm"] = 0.0

# Chi ghi nhung dong co du lieu cam bien
processed = processed.dropna(subset=fields)

if processed.empty:
    print("Khong co du lieu hop le sau tien xu ly.")
    client.close()
    raise SystemExit

# 8. Ghi ket qua vao measurement sensor_processed
saved = 0

for timestamp, row in processed.iterrows():
    point = Point("sensor_processed")
    point = point.tag("device_id", DEVICE_ID)

    for field, value in row.items():
        if pd.notna(value) and np.isfinite(float(value)):
            point = point.field(field, float(value))

    point = point.time(
        timestamp.to_pydatetime(),
        WritePrecision.NS
    )

    write_api.write(
        bucket=BUCKET,
        org=ORG,
        record=point
    )

    saved += 1

print("Tien xu ly hoan tat!")
print("So dong sau tien xu ly:", len(processed))
print("So diem da ghi:", saved)
print("Measurement: sensor_processed")

write_api.close()
client.close()
