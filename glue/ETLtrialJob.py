import os
import sys
import boto3
import pandas as pd
from awsglue.utils import getResolvedOptions

# -----------------------------------
# 1. Get file information from workflow run properties + job arguments
# -----------------------------------
# OUTPUT_BUCKET / DATABASE_NAME / TABLE_NAME come from the Glue job's
# DefaultArguments in cloudformation/template.yaml instead of being
# hard-coded here, so the template stays the single source of truth for
# resource names.
args = getResolvedOptions(
    sys.argv,
    [
        "WORKFLOW_NAME",
        "WORKFLOW_RUN_ID",
        "OUTPUT_BUCKET",
        "DATABASE_NAME",
        "TABLE_NAME",
    ]
)

glue_client = boto3.client("glue")

workflow_run_properties = glue_client.get_workflow_run_properties(
    Name=args["WORKFLOW_NAME"],
    RunId=args["WORKFLOW_RUN_ID"]
)["RunProperties"]

source_bucket = workflow_run_properties["SOURCE_BUCKET"]
source_key = workflow_run_properties["SOURCE_KEY"]

print("Source bucket:", source_bucket)
print("Source key:", source_key)

# -----------------------------------
# 2. Glue Data Catalog configuration
# -----------------------------------

OUTPUT_BUCKET = args["OUTPUT_BUCKET"]
DATABASE_NAME = args["DATABASE_NAME"]
TABLE_NAME = args["TABLE_NAME"]


# -----------------------------------
# 3. Get table information from Glue Catalog
# -----------------------------------

response = glue_client.get_table(
    DatabaseName=DATABASE_NAME,
    Name=TABLE_NAME
)

table = response["Table"]

# S3 location registered in Glue Catalog
catalog_s3_location = table["StorageDescriptor"]["Location"]

# Schema registered in Glue Catalog
catalog_columns = table["StorageDescriptor"]["Columns"]

print("Catalog database:", DATABASE_NAME)
print("Catalog table:", TABLE_NAME)
print("Catalog S3 location:", catalog_s3_location)

print("Catalog schema:")

for column in catalog_columns:
    print(column["Name"], "->", column["Type"])


# -----------------------------------
# 4. Build exact input file path
# -----------------------------------

input_s3_path = f"s3://{source_bucket}/{source_key}"

print("Exact input file:", input_s3_path)


# -----------------------------------
# 5. Read the exact CSV file
# -----------------------------------

df = pd.read_csv(input_s3_path)

print("Input data:")
print(df.head())

print("Input data types:")
print(df.dtypes)


# -----------------------------------
# 5b. Use the catalog schema: flag columns the crawler has on record for
# this table that are missing from this particular file. This is a real
# check now, not just a print - it catches a file that dropped a column the
# catalog still expects (e.g. a schema regression after catalog_run3.csv
# added hazard_type).
# -----------------------------------

catalog_column_names = {column["Name"] for column in catalog_columns}
input_column_names = set(df.columns)

missing_from_input = catalog_column_names - input_column_names

if missing_from_input:
    print(
        "WARNING: catalog has columns this file does not: "
        f"{sorted(missing_from_input)}"
    )
else:
    print("Input file has every column the catalog expects.")


# -----------------------------------
# 6. Convert date from string to datetime
# -----------------------------------

df["date"] = pd.to_datetime(df["date"])

print("Data types after date conversion:")
print(df.dtypes)


# -----------------------------------
# 7. Add year column
# -----------------------------------

df["year"] = df["date"].dt.year

print("Data after transformation:")
print(df.head())


# -----------------------------------
# 8. Write transformed data as Parquet
# -----------------------------------
# Named after the source file instead of a fixed output.parquet, so each
# run's result lands in its own object and later runs stop overwriting
# earlier ones.

source_filename = os.path.splitext(os.path.basename(source_key))[0]
output_path = f"s3://{OUTPUT_BUCKET}/output/{source_filename}.parquet"

df.to_parquet(
    output_path,
    index=False
)

print("Transformation completed successfully.")
print("Output written to:", output_path)
