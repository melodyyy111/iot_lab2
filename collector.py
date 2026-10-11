
print("BAT DAU CHAY COLLECTOR")
import csv
from datetime import datetime
import os
import json
import time
import math
import uuid

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
def save_latency_csv(latency_ms):
    file_exists = os.path.exists("latency.csv")

    with open(
        "latency.csv",
        "a",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "time",
                "latency_ms"
            ])

        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            round(latency_ms, 2)
        ])
# 1. Doc file .env
load_dotenv()

INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")

MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC = os.getenv("MQTT_TOPIC")
DEVICE_ID = os.getenv("DEVICE_ID", "esp32_wokwi_01")

# 2. Kiem tra cau hinh
if not all([
    INFLUX_URL, INFLUX_ORG, INFLUX_BUCKET,
    INFLUX_TOKEN, MQTT_HOST, MQTT_TOPIC
]):
    raise ValueError(
        "Thieu cau hinh trong .env. "
        "Hay kiem tra INFLUX va MQTT."
    )

if not 1 <= MQTT_PORT <= 65535:
    raise ValueError("MQTT_PORT khong hop le")

print("InfluxDB URL:", INFLUX_URL)
print("InfluxDB bucket:", INFLUX_BUCKET)
print("MQTT broker:", MQTT_HOST)
print("MQTT port:", MQTT_PORT)
print("MQTT topic:", MQTT_TOPIC)
print("Device ID:", DEVICE_ID)

# 3. Ket noi InfluxDB
db_client = InfluxDBClient(
    url=INFLUX_URL,
    token=INFLUX_TOKEN,
    org=INFLUX_ORG,
    timeout=10000
)

write_api = db_client.write_api(
    write_options=SYNCHRONOUS
)

# Kiem tra InfluxDB
try:
    if not db_client.ping():
        raise ConnectionError("InfluxDB khong phan hoi")

    print("InfluxDB ket noi thanh cong!")

except Exception as error:
    db_client.close()
    raise RuntimeError(
        "Khong ket noi duoc InfluxDB: " + str(error)
    )

# 4. Bien thong ke
received_count = 0
saved_count = 0
invalid_count = 0
last_sequence = None
latency_list = []

# 5. Khi MQTT ket noi
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("\nMQTT KET NOI THANH CONG!")

        result, mid = client.subscribe(MQTT_TOPIC, qos=0)

        if result == mqtt.MQTT_ERR_SUCCESS:
            print("DANG KY TOPIC:", MQTT_TOPIC)
            print("Dang cho ESP32 gui du lieu...")
        else:
            print("DANG KY TOPIC THAT BAI:", result)

    else:
        print("MQTT KET NOI THAT BAI:", reason_code)


# 6. Khi MQTT mat ket noi
def on_disconnect(
    client, userdata, disconnect_flags, reason_code, properties
):
    print("\nMQTT BI NGAT KET NOI!")
    print("Ma ly do:", reason_code)
    print("Paho se thu ket noi lai neu loop dang hoat dong.")


# 7. Khi nhan duoc du lieu
def on_message(client, userdata, msg):
    global received_count, saved_count
    global invalid_count, last_sequence

    start_time = time.perf_counter()
    received_count += 1

    print("\n================================")
    print("NHAN DUOC MQTT!")
    print("Topic:", msg.topic)

    try:
        # Doc JSON
        data = json.loads(msg.payload.decode("utf-8"))
        print("Du lieu:", data)

        if not isinstance(data, dict):
            raise ValueError("JSON phai la object")

        # Cac truong bat buoc
        required_fields = [
            "temperature",
            "humidity",
            "distance_cm"
        ]

        values = {}

        for field in required_fields:
            if field not in data:
                raise ValueError("Thieu truong: " + field)

            value = data[field]

            if isinstance(value, bool) or not isinstance(
                value, (int, float)
            ):
                raise ValueError(field + " phai la so")

            if not math.isfinite(value):
                raise ValueError(field + " khong hop le")

            if not -1000000 < value < 1000000:
                raise ValueError(field + " nam ngoai gioi han")

            values[field] = float(value)

        # Cac truong tuy chon
        for field in ["rssi", "sequence", "uptime_s"]:
            if field in data:
                value = data[field]

                if isinstance(value, bool) or not isinstance(
                    value, (int, float)
                ):
                    raise ValueError(field + " phai la so")

                if not math.isfinite(value):
                    raise ValueError(field + " khong hop le")

                values[field] = value

        # Kiem tra sequence
        if "sequence" in values:
            sequence = values["sequence"]

            if int(sequence) != sequence or sequence < 0:
                raise ValueError("sequence khong hop le")

            sequence = int(sequence)

            if last_sequence is not None:
                if sequence > last_sequence + 1:
                    print(
                        "CANH BAO: Co the mat",
                        sequence - last_sequence - 1,
                        "goi tin"
                    )

            last_sequence = sequence

        # Tao ban ghi
        point = Point("sensor_data")
        point = point.tag("device_id", DEVICE_ID)

        for field, value in values.items():
            point = point.field(field, value)

        # Do tre tu ESP32 neu timestamp hop le
        sent_at_ms = data.get("sent_at_ms")
        receive_latency = None

        if (
            isinstance(sent_at_ms, (int, float))
            and not isinstance(sent_at_ms, bool)
            and math.isfinite(sent_at_ms)
        ):
            receive_latency = time.time() * 1000 - sent_at_ms

            if 0 <= receive_latency <= 600000:
                point = point.field(
                    "receive_latency_ms",
                    float(receive_latency)
                )
            else:
                receive_latency = None

        # Gan thoi gian ghi
        point = point.time(time.time_ns(), WritePrecision.NS)

        # Ghi InfluxDB dung mot lan
        write_api.write(
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG,
            record=point
        )

        # Do tong thoi gian xu ly va ghi
        elapsed_ms = (
            time.perf_counter() - start_time
        ) * 1000

        saved_count += 1
        latency_list.append(elapsed_ms)
        save_latency_csv(elapsed_ms)
        print("Da ghi do tre vao latency.csv")
        print("GHI INFLUXDB THANH CONG!")
        print("Do tre xu ly + ghi DB: {:.2f} ms".format(elapsed_ms))

        if receive_latency is not None:
            print(
                "Do tre ESP32 -> Collector: {:.2f} ms".format(
                    receive_latency
                )
            )
        else:
            print(
                "Khong co sent_at_ms hop le; "
                "khong tinh duoc do tre tu ESP32."
            )

        print(
            "Tong nhan:", received_count,
            "| Da luu:", saved_count,
            "| Loi:", invalid_count
        )

        print(
            "Do tre trung binh: {:.2f} ms".format(
                sum(latency_list) / len(latency_list)
            )
        )
        print(
            "Do tre nho nhat: {:.2f} ms".format(
                min(latency_list)
            )
        )
        print(
            "Do tre lon nhat: {:.2f} ms".format(
                max(latency_list)
            )
        )

    except Exception as error:
        invalid_count += 1
        print("LOI XU LY GOI TIN:", repr(error))


# 8. Tao MQTT client voi client ID rieng
client_id = "ptit-collector-" + uuid.uuid4().hex[:8]

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id=client_id,
    protocol=mqtt.MQTTv311
)

if MQTT_USERNAME:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message

# 9. Ket noi va cho du lieu
try:
    print("\nDang ket noi MQTT...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever(retry_first_connection=True)

except KeyboardInterrupt:
    print("\nDa dung Collector theo yeu cau.")

except Exception as error:
    print("LOI KET NOI MQTT:", repr(error))

finally:
    try:
        client.disconnect()
    except Exception:
        pass

    write_api.close()
    db_client.close()
    print("Da dong Collector va InfluxDB.")
