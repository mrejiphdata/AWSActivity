import json
import time
import boto3
import urllib.parse
from botocore.exceptions import ClientError

glue_client = boto3.client("glue")

WORKFLOW_NAME = "github-aws-activity-workflow"

# The workflow allows a few concurrent runs (see MaxConcurrentRuns in
# cloudformation/template.yaml), but if enough files land at almost the same
# moment even that limit can be hit. Retry a few times with a short delay
# instead of dropping the file on the floor.
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5


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

    response = start_workflow_with_retry(bucket, key)

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


def start_workflow_with_retry(bucket, key):
    """
    Start the workflow run, retrying on ConcurrentRunsExceededException.

    If every retry is exhausted, re-raise the error so the Lambda invocation
    fails - S3's async invocation of this Lambda already retries a failed
    invocation twice more on its own (with a delay), which gives a second
    line of defense on top of this one.
    """

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return glue_client.start_workflow_run(
                Name=WORKFLOW_NAME,
                RunProperties={
                    "SOURCE_BUCKET": bucket,
                    "SOURCE_KEY": key
                }
            )

        except ClientError as error:
            error_code = error.response["Error"]["Code"]

            if error_code != "ConcurrentRunsExceededException":
                raise

            last_error = error

            print(
                f"Attempt {attempt}/{MAX_ATTEMPTS}: workflow is already at "
                f"its concurrent run limit, retrying in "
                f"{RETRY_DELAY_SECONDS}s"
            )

            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    raise last_error
