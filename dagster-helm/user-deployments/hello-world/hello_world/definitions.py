from dagster import Definitions, job, op


@op
def hello_world_op(context):
    context.log.info("Hello, world!")
    return "Hello, world!"


@job
def hello_world_job():
    hello_world_op()


defs = Definitions(jobs=[hello_world_job])
