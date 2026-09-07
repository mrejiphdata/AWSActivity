import pandas as pd
from pathlib import Path

# Create a folder for the CSV files
output_dir = Path("glue_test_data")
output_dir.mkdir(exist_ok=True)


# ==========================================
# CSV 1 - Initial schema (4 columns)
# ==========================================

data1 = [
    [1, "3/2/07", "United States", 16000],
    [2, "3/22/07", "United States", 17288],
    [3, "4/10/07", "Canada", 12000],
    [4, "5/15/07", "India", 25000],
    [5, "6/12/07", "Australia", 18000],
    [6, "7/20/07", "Germany", 14000],
    [7, "8/3/07", "France", 22000],
    [8, "9/11/07", "Japan", 19000],
    [9, "10/2/07", "Brazil", 27000],
    [10, "11/14/07", "United Kingdom", 15500]
]

df1 = pd.DataFrame(
    data1,
    columns=["id", "date", "country", "population"]
)

df1.to_csv(output_dir / "catalog_run1.csv", index=False)


# ==========================================
# CSV 2 - Same schema (4 columns)
# ==========================================

data2 = [
    [11, "12/5/07", "United States", 21000],
    [12, "1/18/08", "Canada", 13500],
    [13, "2/10/08", "India", 31000],
    [14, "3/25/08", "Australia", 19500],
    [15, "4/12/08", "Germany", 16000],
    [16, "5/8/08", "France", 23000],
    [17, "6/19/08", "Japan", 20500],
    [18, "7/7/08", "Brazil", 28500],
    [19, "8/21/08", "United Kingdom", 17000],
    [20, "9/15/08", "Italy", 14500]
]

df2 = pd.DataFrame(
    data2,
    columns=["id", "date", "country", "population"]
)

df2.to_csv(output_dir / "catalog_run2.csv", index=False)


# ==========================================
# CSV 3 - Schema evolution (5 columns)
# Added: hazard_type
# ==========================================

data3 = [
    [21, "10/3/08", "United States", 22000, "Landslide"],
    [22, "11/17/08", "Canada", 14500, "Flood"],
    [23, "12/8/08", "India", 32000, "Landslide"],
    [24, "1/22/09", "Australia", 20000, "Flood"],
    [25, "2/14/09", "Germany", 17500, "Storm"],
    [26, "3/30/09", "France", 24000, "Landslide"],
    [27, "4/16/09", "Japan", 21500, "Earthquake"],
    [28, "5/25/09", "Brazil", 29500, "Flood"],
    [29, "6/11/09", "United Kingdom", 18000, "Storm"],
    [30, "7/19/09", "Italy", 15500, "Landslide"]
]

df3 = pd.DataFrame(
    data3,
    columns=["id", "date", "country", "population", "hazard_type"]
)

df3.to_csv(output_dir / "catalog_run3.csv", index=False)


print("3 CSV files created successfully!")
print(f"Files are located in: {output_dir.absolute()}")