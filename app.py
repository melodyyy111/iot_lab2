
import os
import pandas as pd
import streamlit as st
import plotly.express as px

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

# Doc cau hinh tu file .env
load_dotenv()

URL = os.getenv("INFLUX_URL")
ORG = os.getenv("INFLUX_ORG")
BUCKET = os.getenv("INFLUX_BUCKET")
TOKEN = os.getenv("INFLUX_TOKEN")
DEVICE_ID = os.getenv("DEVICE_ID", "esp32_wokwi_01")

st.set_page_config(
    page_title="IoT Lab 2",
    page_icon="🌡️",
    layout="wide"
)

st.title("Dashboard giam sat IoT")
st.caption("Du lieu cam bien va ket qua tien xu ly")

if not all([URL, ORG, BUCKET, TOKEN]):
    st.error("Thieu cau hinh InfluxDB. Hay kiem tra file .env.")
    st.stop()


@st.cache_data(ttl=5)
def get_data(measurement, bucket, org, url, token, device_id):
    query = f'''
    from(bucket: "{bucket}")
        |> range(start: -24h)
        |> filter(fn: (r) => r._measurement == "{measurement}")
        |> filter(fn: (r) => r.device_id == "{device_id}")
        |> pivot(
            rowKey: ["_time"],
            columnKey: ["_field"],
            valueColumn: "_value"
        )
        |> sort(columns: ["_time"])
    '''

    with InfluxDBClient(url=url, token=token, org=org) as client:
        tables = client.query_api().query_data_frame(
            query=query,
            org=org
        )

    if isinstance(tables, list):
        frames = [
            item for item in tables
            if isinstance(item, pd.DataFrame) and not item.empty
        ]
        if not frames:
            return pd.DataFrame()
        data = pd.concat(frames, ignore_index=True)
    else:
        data = tables

    if data.empty or "_time" not in data.columns:
        return pd.DataFrame()

    data["_time"] = pd.to_datetime(data["_time"], utc=True)
    return data.sort_values("_time")


try:
    raw = get_data(
        "sensor_data", BUCKET, ORG, URL, TOKEN, DEVICE_ID
    )

    processed = get_data(
        "sensor_processed", BUCKET, ORG, URL, TOKEN, DEVICE_ID
    )

except Exception as e:
    st.error("Khong doc duoc du lieu tu InfluxDB.")
    st.code(str(e))
    st.stop()


# Chon loai du lieu muon xem
mode = st.radio(
    "Loai du lieu",
    ["Du lieu goc", "Du lieu sau tien xu ly"],
    horizontal=True
)

if mode == "Du lieu goc":
    data = raw
else:
    data = processed

if data.empty:
    st.warning(
        "Chua co du lieu. Hay kiem tra collector.py, "
        "preprocess.py va DEVICE_ID trong file .env."
    )
    st.stop()


# Cac chi so tong quan
st.subheader("Thong tin tong quan")

c1, c2, c3 = st.columns(3)

if "temperature" in data.columns:
    c1.metric(
        "Nhiet do moi nhat",
        f"{data['temperature'].dropna().iloc[-1]:.1f} °C"
        if data["temperature"].notna().any() else "Chua co"
    )
else:
    c1.metric("Nhiet do moi nhat", "Chua co")

if "humidity" in data.columns:
    c2.metric(
        "Do am moi nhat",
        f"{data['humidity'].dropna().iloc[-1]:.1f} %"
        if data["humidity"].notna().any() else "Chua co"
    )
else:
    c2.metric("Do am moi nhat", "Chua co")

if "distance_cm" in data.columns:
    c3.metric(
        "Khoang cach moi nhat",
        f"{data['distance_cm'].dropna().iloc[-1]:.1f} cm"
        if data["distance_cm"].notna().any() else "Chua co"
    )
else:
    c3.metric("Khoang cach moi nhat", "Chua co")


# Ve bieu do
st.subheader("Bieu do cam bien")

for field, title, unit in [
    ("temperature", "Nhiet do", "°C"),
    ("humidity", "Do am", "%"),
    ("distance_cm", "Khoang cach", "cm")
]:
    if field in data.columns and data[field].notna().any():
        chart_data = data[["_time", field]].dropna()

        fig = px.line(
            chart_data,
            x="_time",
            y=field,
            title=title,
            labels={
                "_time": "Thoi gian",
                field: f"{title} ({unit})"
            }
        )

        st.plotly_chart(fig, use_container_width=True)


# Hien thi bang du lieu
st.subheader("Bang du lieu")
st.dataframe(data, use_container_width=True)

st.caption(
    f"So dong hien thi: {len(data)} | "
    f"Thiet bi: {DEVICE_ID} | "
    "Khoang thoi gian truy van: 24 gio"
)

if st.button("Lam moi du lieu"):
    get_data.clear()
    st.rerun()
