from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@workflow.defn
class DocumentWorkflow:
    @workflow.run
    async def run(self, job_id: str):
        try:
            await workflow.execute_activity(
                "process_document",
                job_id,
                start_to_close_timeout=timedelta(hours=4),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    maximum_attempts=3, initial_interval=timedelta(seconds=5)
                ),
            )
        except ActivityError:
            await workflow.execute_activity(
                "record_workflow_failure",
                job_id,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    maximum_attempts=10, initial_interval=timedelta(seconds=5)
                ),
            )


@workflow.defn
class CaseSOPWorkflow:
    @workflow.run
    async def run(self, run_id: str):
        try:
            await workflow.execute_activity(
                "process_case_sop",
                run_id,
                start_to_close_timeout=timedelta(minutes=15),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    maximum_attempts=3, initial_interval=timedelta(seconds=5)
                ),
            )
        except ActivityError:
            await workflow.execute_activity(
                "record_case_failure",
                run_id,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=10),
            )
