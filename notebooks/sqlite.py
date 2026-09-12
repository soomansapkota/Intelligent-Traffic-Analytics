import sqlite3
import pandas as pd

connection = sqlite3.connect("data/traffic.db")

with pd.ExcelWriter("metro_data.xlsx", engine="openpyxl") as writer:
    for table in ["trip_updates", "vehicle_positions", "alerts"]:
        data = pd.read_sql_query(f"SELECT * FROM {table}", connection)
        data.to_excel(writer, sheet_name=table[:31], index=False)

connection.close()