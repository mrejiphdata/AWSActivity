import sys
import boto3
import pandas as pd
from awsglue.utils import getResolvedOptions

# -----------------------------------
# 1. Get file information from workflow run properties
# -----------------------------------
args = getResolvedOptions(
    sys.argv,
    ["WORKFLOW_NAME", "WORKFLOW_RUN_ID"]
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

DATABASE_NAME = "github_aws_activity_db"
TABLE_NAME = "input"

glue_client = boto3.client("glue")


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

output_path = "s3://github-aws-activity-output/output/output.parquet"

df.to_parquet(
    output_path,
    index=False
)

print("Transformation completed successfully.")
print("Output written to:", output_path)