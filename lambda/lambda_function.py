import json
import boto3
import urllib.parse

glue_client = boto3.client("glue")

WORKFLOW_NAME = "github-aws-activity-workflow"


def lambda_handler(event, context):

    record = event["Records"][0]

    bucket = record["s3"]["bucket"]["name"]

    key = urllib.parse.unquote_plus(
        record["s3"]["object"]["key"]
    )

    print("Bucket:", bucket)
    print("File:", key)

    if not key.lower().endswith(".csv"):
        return {
            "statusCode": 200,
            "body": json.dumps("Not a CSV file")
        }

    response = glue_client.start_workflow_run(
        Name=WORKFLOW_NAME,
        RunProperties={
            "SOURCE_BUCKET": bucket,
            "SOURCE_KEY": key
        }
    )

    print("Workflow started:", response["RunId"])

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Glue Workflow started",
            "workflow_run_id": response["RunId"],
            "source_bucket": bucket,
            "source_key": key
        })
    }