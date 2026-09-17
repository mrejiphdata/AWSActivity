# GitHub AWS Activity — Serverless CSV ETL Pipeline

An event-driven pipeline that watches an S3 bucket for new CSV files, catalogs and transforms
them with AWS Glue, and lands the result as Parquet in an output bucket. Every AWS resource is
defined in one CloudFormation template, and a GitHub Actions workflow deploys it on every push.

## Architecture

![alt text](AwsActivity.drawio.png)

## Architecture of glue job
![alt text](<Pythonshelljob.drawio (1).png>)

### Step by step

**1. A CSV lands in the input bucket.** Files are expected under the `input/` prefix with a
`.csv` suffix — for example `s3://github-aws-activity-input/input/catalog_run1.csv`. That
prefix/suffix pair is the exact filter configured on the bucket notification, so anything
outside `input/*.csv` is ignored.

**2. S3 invokes the Lambda directly.** The bucket's notification configuration points at
`github-aws-activity-lambda` for every `s3:ObjectCreated:*` event matching that filter. An
`AWS::Lambda::Permission` resource grants `s3.amazonaws.com` permission to invoke the function;
without it S3 would silently fail to call it.

**3. The Lambda starts a Glue workflow run.** `lambda/lambda_function.py` reads the bucket and
key off the S3 event, checks the extension is `.csv`, and calls
`glue_client.start_workflow_run()` on `github-aws-activity-workflow`, passing the exact bucket
and key as `RunProperties` (`SOURCE_BUCKET`, `SOURCE_KEY`). That's the mechanism that lets a
Python Shell job — which has no native S3-event trigger of its own — know precisely which file
just arrived, instead of rescanning the whole bucket.

**4. Starting the workflow fires its ON_DEMAND trigger.** `StartTrigger` is the workflow's entry
point; its one action is running `github-aws-activity-crawler` against
`s3://github-aws-activity-input/input/`. The crawler inspects the CSV's schema and creates or
updates a table in the Glue Data Catalog database `github_aws_activity_db` — this is what lets
schema drift (like the extra `hazard_type` column in `catalog_run3.csv`) get picked up
automatically rather than breaking downstream reads.

**5. Crawler success fires the ETL job.** `CrawlerSuccessTrigger` is a `CONDITIONAL` trigger that
watches for the crawler to reach `CrawlState: SUCCEEDED`, then starts
`github-aws-activity-etl`, a Glue Python Shell job (`glue/ETLtrialJob.py`).

![alt text](<Screenshot 2026-09-07 221508.png>)

**6. The job transforms only the new file.** Rather than processing every file in the bucket,
the job calls `get_workflow_run_properties()` to retrieve the `SOURCE_BUCKET`/`SOURCE_KEY` the
Lambda set in step 3, reads exactly that object with pandas, parses the `date` column, derives a
`year` column, and writes the result as Parquet named after the source file (for example
`s3://github-aws-activity-output/output/catalog_run1.parquet`), so each run keeps its own output
instead of overwriting the last one. The output bucket, catalog database and table names are
passed into the job as arguments from `cloudformation/template.yaml` rather than hard-coded in
`ETLtrialJob.py`.

Each of these five hand-offs is an independent AWS service reacting to a state change in the
previous one — S3 notification → Lambda invocation → Glue workflow run → crawler completion →
job start — rather than one long-running process, which is what makes the whole thing
serverless and pay-per-event.

![alt text](<Screenshot 2026-09-07 222347.png>)

## What the CloudFormation stack owns

`cloudformation/template.yaml` is deployed as a single stack (`github-aws-activity-stack`) and
is the only source of truth for every resource above. Nothing in this pipeline is created by
hand or by ad-hoc CLI calls anymore — it's all provisioned, updated, and torn down as one unit:

- **S3 buckets** — `InputBucket` and `OutputBucket`, both with public access fully blocked.
- **IAM roles** — each Lambda has its own role (`S3NotificationRole` for the notification-wiring
  helper, `ProcessingLambdaRole` for the one that starts the workflow) instead of sharing one, and
  `GlueRole` for the crawler and job. Every role's inline policy is scoped to just the specific
  buckets, Glue resources (by name, not `*`), and log groups it needs.
- **Glue Data Catalog** — the database, the crawler, and the Python Shell job.
- **Glue Workflow and triggers** — the workflow itself, the `ON_DEMAND` `StartTrigger`, and the
  `CONDITIONAL` `CrawlerSuccessTrigger`.
- **Two Lambda functions** — `github-aws-activity-lambda` (the actual event handler described
  above) and `S3NotificationFunction`, a small helper.
- **The S3 → Lambda wiring** — an `AWS::Lambda::Permission` plus a custom resource,
  `ConfigureBucketNotification`.

One bucket deliberately isn't part of the stack: `github-aws-activity-lambda-artifacts` holds the
zipped `lambda/lambda_function.py` that the processing Lambda's `Code` property points at.
`InputBucket` is created *by* this stack, so if the Lambda code lived there too, a from-scratch
deploy (e.g. right after `destroy.yml`) would need the zip uploaded before the bucket that's
supposed to hold it exists yet. The artifacts bucket is created once, outside the stack
(`deploy.yml` creates it if missing, idempotently, on every run), and is never touched by
`destroy.yml` — it just persists across every destroy/deploy cycle.

### Why there's a second, "invisible" Lambda

CloudFormation has no native `AWS::S3::BucketNotification` resource, and setting a
`NotificationConfiguration` directly on the `AWS::S3::Bucket` resource would create a circular
dependency (the bucket would need to know the Lambda's ARN, and the Lambda's permission would
need to know the bucket's ARN, each waiting on the other). The template works around this with a
custom resource: `S3NotificationFunction` is a tiny Lambda whose only job is to call
`put_bucket_notification_configuration()` on the input bucket, pointed at the *real* Lambda's
ARN. CloudFormation invokes it once after the bucket, the real Lambda, and its invoke permission
all exist (`ConfigureBucketNotification`'s `DependsOn`), and again on stack deletion to clear the
notification before the bucket is removed. It never appears in the AWS Console's list of things
you "use" — it only exists to do this one wiring step during deploys and teardowns.

## What's automated in the pipeline

Four GitHub Actions workflows cover the full lifecycle — nothing needs to be run from a local
terminal:

| Workflow | Trigger | What it does |
|---|---|---|
| `deploy.yml` | Push to `main` touching the template, Lambda, or Glue script; or manual | Zips and uploads `lambda/lambda_function.py` (content-hashed S3 key), validates and deploys the CloudFormation stack, uploads `glue/ETLtrialJob.py` to the input bucket's `scripts/` prefix, then verifies every resource exists. |
| `process.yml` | Manual, pick one of the three sample CSVs | Uploads a single CSV to `input/`, which is the real end-to-end trigger for the whole pipeline described above. |
| `destroy.yml` | Manual, requires typing `DESTROY` | Empties both S3 buckets, deletes the CloudFormation stack, waits for deletion to finish, cleans up the two Lambda log groups CloudFormation doesn't own, and confirms the stack is gone. |

`deploy.yml` is the only one that runs automatically; the other two are deliberately manual
(`workflow_dispatch`) since uploading test data or tearing down infrastructure shouldn't happen
on every push.

All three workflows authenticate to AWS using the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
repository secrets. (OIDC federation - so no long-lived keys are stored in GitHub at all - was
evaluated, but this AWS account has an Organization-level SCP that denies
`iam:CreateOpenIDConnectProvider`/`iam:ListOpenIDConnectProviders`, so it can't be enabled without
an org admin lifting that restriction first.)

## How this project got here

The pipeline went through three distinct phases, visible in the repo's git history:

1. **Manual setup.** The buckets, IAM roles, Glue database/crawler/job/workflow, and Lambda were
   first created by hand in the AWS Console to prove the design worked end to end.

2. **A plain GitHub Actions pipeline.** That manual setup was then translated, step by step,
   into an imperative `deploy.yml` that ran `aws` CLI commands directly — creating trust
   policies, IAM roles and managed policies, the buckets, the Glue database/crawler/job/workflow
   and the Lambda, one `aws iam create-role` / `aws glue create-crawler` / etc. call at a time.

3. **CloudFormation.** The imperative CLI steps were replaced with the single declarative
   template now in `cloudformation/template.yaml`, and `deploy.yml` shrank to essentially one
   command: `aws cloudformation deploy`. This is what makes `destroy.yml` possible —
   CloudFormation tracks every resource it created as one stack, so tearing it down is one
   `delete-stack` call instead of manually reversing a dozen CLI commands in the right order.

## Feedback addressed

A review of an earlier version of this project raised eight points. Here's what changed in
response to each:

| # | Feedback | What changed |
|---|---|---|
| 1 | Every run overwrote `output/output.parquet`, so only the last run's result survived. | `ETLtrialJob.py` now names the output after the source file (e.g. `output/catalog_run1.parquet`), so each run keeps its own file. |
| 2 | The workflow only allowed 1 concurrent run, so two CSVs uploaded together could cause the second to be skipped. | `GlueWorkflow.MaxConcurrentRuns` raised to 5, and `lambda_function.py` retries `start_workflow_run` up to 3 times (with backoff) on `ConcurrentRunsExceededException` before giving up. |
| 3 | AWS access keys were stored as GitHub secrets. | Attempted OIDC federation (a `GithubActionsDeployRole` trusted via GitHub's OIDC provider, no long-lived keys needed). Blocked: this AWS account has an Organization-level SCP that denies `iam:CreateOpenIDConnectProvider`/`ListOpenIDConnectProviders`, so the provider can't be created without an org admin lifting that restriction. Reverted to the original `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` secrets for now. |
| 4 | Both Lambdas shared one over-permissioned role; the Glue role allowed its actions on all resources (`*`). | Split into `S3NotificationRole` (bucket-notification wiring only) and `ProcessingLambdaRole` (starts the workflow only, no S3 access). `GlueRole`'s Glue actions are now scoped to this project's specific database/table/crawler/job/workflow ARNs instead of `*`. |
| 5 | Output bucket, database, and table names were typed directly into `ETLtrialJob.py`. | Passed in as Glue job arguments (`--OUTPUT_BUCKET`, `--DATABASE_NAME`, `--TABLE_NAME`) from `cloudformation/template.yaml`, read via `getResolvedOptions`. Nothing hard-coded in the script anymore. |
| 6 | The job read the table schema from the Glue Catalog but only printed it. | Now compares catalog columns against the incoming file's columns and logs a warning if the file is missing a column the catalog expects — a real schema-drift check instead of a print statement. |
| 7 | Lambda code lived in two places (inline in the template and in `lambda/lambda_function.py`), risking drift. | `deploy.yml` zips and uploads `lambda/lambda_function.py` to S3; the template's `LambdaFunction` references that S3 object instead of an inline `ZipFile`. One copy of the code. |
| 8 | Unused `policies/` folder, one-time `cleanup-legacy.yml`, and an unused `GlueDatabaseName` override in `deploy.yml`. | All three removed. Screenshot renaming was intentionally left for later. |

One additional fix came out of rolling this out: deploying the Lambda from S3 introduced a
bootstrap ordering problem (uploading the code to `InputBucket` before the same stack has created
that bucket, e.g. right after a `destroy.yml` run). Fixed by giving the Lambda code its own
bucket, `github-aws-activity-lambda-artifacts`, created once and left outside the stack entirely
so it survives every destroy/deploy cycle — see "What the CloudFormation stack owns" above.

## Repository layout

```
cloudformation/template.yaml    CloudFormation stack — every AWS resource described above
lambda/lambda_function.py       The processing Lambda's code — zipped and uploaded to S3 by
                                 deploy.yml, and the only copy of it (nothing inlined anymore)
glue/ETLtrialJob.py             The Glue Python Shell ETL job
CreatingCSV/                    CSVCreation.py generates the 3 sample CSVs used by process.yml
.github/workflows/              deploy.yml, process.yml, destroy.yml
```

## Running it

- **Deploy:** push to `main` with a change under `cloudformation/`, `glue/`, or `lambda/`, or run
  `deploy.yml` manually from the Actions tab.
- **Test the trigger:** run `process.yml` manually and pick one of `catalog_run1.csv`,
  `catalog_run2.csv`, or `catalog_run3.csv`. Watch the Lambda's CloudWatch log group
  (`/aws/lambda/github-aws-activity-lambda`) and the workflow's run history in the Glue console
  to follow it through the crawler and the ETL job.
- **Tear down:** run `destroy.yml` manually, typing `DESTROY` when prompted. No local AWS CLI
  access is needed for any of this.

# first run:
![alt text](<CSVProcessPipeline.png>)
![alt text](<lambdaFunc.png>)
![alt text](<lambdaFuncOverview.png>)
# output in paraquet format:
![alt text](<OutputFile.png>)

# github actions:
![alt text](<GithubActions.png>)

# pipelines:
![alt text](<DeployPipeline.png>)

![alt text](<ProcessPipeline.png>)

# on running destroy pipeline:
![alt text](<DestroyPipeline.png>)

![alt text](<AfterDestroy.png>)

# after that running the deploy pipeline again:
![alt text](<DeployPipeline_AfterDestroy.png>)

## running the pipeline to uplad csv-first csv file with 4 columns
![alt text](<CSV1.png>)

# buckets created
![alt text](<Buckets.png>)

# input bucket
![alt text](<InputBucket.png>)

# crawler loading to catalog
![alt text](<CrawlerTable.png>)



## running the pipeline to uplad csv-third csv file with 5 columns

# input bucket:
![alt text](<inputBucketSecondCSV.png>)

# same catalog gets updated 
![alt text](<CatalogUpdation.png>)

![alt text](<OutputSecondCSV.png>)

# updated output bucket name
![alt text](image.png)