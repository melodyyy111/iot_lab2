
import os
import pandas as pd
import matplotlib.pyplot as plt

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

# =================================
# 1. DOC CAU HINH INFLUXDB
# =================================

load_dotenv()

INFLUX_URL = os.getenv(
    "INFLUX_URL",
    "http://localhost:8086"
)

INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot_lab")

print("BAT DAU TRUC QUAN HOA DU LIEU IOT")

# =================================
# 2. KET NOI INFLUXDB
# =================================

client = InfluxDBClient(
    url=INFLUX_URL,
    token=INFLUX_TOKEN,
    org=INFLUX_ORG
)

query_api = client.query_api()

# =================================
# 3. TRUY VAN DU LIEU
# =================================

query = '''
from(bucket: "''' + INFLUX_BUCKET + '''")
    |> range(start: -24h)
    |> filter(fn: (r) => r["_measurement"] == "sensor_data")
    |> filter(fn: (r) =>
        r["_field"] == "temperature" or
        r["_field"] == "humidity" or
        r["_field"] == "distance"
    )
    |> sort(columns: ["_time"])
'''

try:
    print("Dang doc du lieu tu InfluxDB...")

    tables = query_api.query_data_frame(
        query=query,
        org=INFLUX_ORG
    )

    # InfluxDB co the tra ve mot DataFrame
    # hoac mot danh sach DataFrame
    if isinstance(tables, list):
        frames = [
            frame for frame in tables
            if not frame.empty
        ]

        if frames:
            df = pd.concat(frames, ignore_index=True)
        else:
            df = pd.DataFrame()
    else:
        df = tables

    if df.empty:
        print("Khong co du lieu trong 24 gio gan nhat.")
        print("Hay kiem tra bucket va measurement sensor_data.")

    else:
        print("Doc du lieu thanh cong!")
        print("So ban ghi:", len(df))

        # =================================
        # 4. CHUAN BI DU LIEU
        # =================================

        df = df.dropna(subset=["_time", "_value"])

        df["_time"] = pd.to_datetime(
            df["_time"],
            utc=True
        )

        # Chuyen du lieu dang cot thanh dang hang
        data = df.pivot_table(
            index="_time",
            columns="_field",
            values="_value",
            aggfunc="mean"
        )

        data = data.sort_index()

        print("\nCac thong so tim thay:")
        print(list(data.columns))

        # =================================
        # 5. VE BIEU DO
        # =================================

        sensors = [
            "temperature",
            "humidity",
            "distance"
        ]

        available_sensors = [
            sensor for sensor in sensors
            if sensor in data.columns
        ]

        if not available_sensors:
            print("Khong tim thay cac truong cam bien da cau hinh.")
            print("Hay kiem tra ten field trong InfluxDB.")

        else:
            fig, axes = plt.subplots(
                len(available_sensors),
                1,
                figsize=(12, 4 * len(available_sensors))
            )

            # Neu chi co mot bieu do
            # thi axes khong phai danh sach
            if len(available_sensors) == 1:
                axes = [axes]

            for i, sensor in enumerate(available_sensors):
                axes[i].plot(
                    data.index,
                    pd.to_numeric(
                        data[sensor],
                        errors="coerce"
                    ),
                    marker="o",
                    markersize=3
                )

                axes[i].set_title(
                    "Du lieu cam bien: " + sensor
                )

                axes[i].set_xlabel("Thoi gian")
                axes[i].set_ylabel(sensor)
                axes[i].grid(True)

            plt.tight_layout()

            # Luu anh bieu do
            plt.savefig(
                "iot_visualization.png",
                dpi=150,
                bbox_inches="tight"
            )

            print("\nDa luu bieu do: iot_visualization.png")

            # Hien thi bieu do
            plt.show()

except Exception as e:
    print("Loi khi doc hoac ve du lieu:", e)

finally:
    client.close()
    print("Da dong ket noi InfluxDB.")
