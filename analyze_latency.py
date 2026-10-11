
print("BAT DAU PHAN TICH DO TRE")

import os
import pandas as pd

print("Thu muc hien tai:", os.getcwd())

if not os.path.exists("latency.csv"):
    print("KHONG TIM THAY latency.csv")
    print("Hay chay collector.py va cho ESP32 gui du lieu.")
else:
    print("Da tim thay latency.csv")

    df = pd.read_csv("latency.csv")

    print("So dong doc duoc:", len(df))

    if df.empty:
        print("File CSV chua co du lieu.")
    elif "latency_ms" not in df.columns:
        print("Thieu cot latency_ms.")
        print("Cac cot hien co:", list(df.columns))
    else:
        latency = pd.to_numeric(
            df["latency_ms"],
            errors="coerce"
        ).dropna()

        if latency.empty:
            print("Khong co gia tri do tre hop le.")
        else:
            print("\n===== THONG KE DO TRE =====")
            print("So mau:", len(latency))
            print("Trung binh: {:.2f} ms".format(latency.mean()))
            print("Nho nhat: {:.2f} ms".format(latency.min()))
            print("Lon nhat: {:.2f} ms".format(latency.max()))
            print("Trung vi: {:.2f} ms".format(latency.median()))

print("\nDA KET THUC PHAN TICH")
