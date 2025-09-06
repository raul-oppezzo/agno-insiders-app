from dotenv import load_dotenv
from argparse import ArgumentParser

from agno.utils.log import logger
from agno.workflow import RunResponse

from exceptions.exceptions import WorkflowException
from workflows.insiders_workflow_v2 import InsidersWorkflow

load_dotenv()


def main(company_name: str, report_url: str) -> None:
    workflow = InsidersWorkflow()

    try:
        response: RunResponse = workflow.run(
            company_name=company_name, report_url=report_url
        )
        logger.info(response.content)
    except WorkflowException as e:
        logger.error("Workflow error.")
        logger.error(str(e))
        return
    except Exception as e:
        logger.error("Unexpected error.")
        logger.error(str(e))
        return


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-c",
        "--company_name",
        type=str,
        required=False,
    )
    parser.add_argument(
        "--report_url",
        type=str,
        required=False,
        default=None,
    )

    args = parser.parse_args()
    if not args.company_name and not args.report_url:
        parser.error("At least one of --company_name or --report_url must be provided.")

    main(args.company_name, args.report_url)
