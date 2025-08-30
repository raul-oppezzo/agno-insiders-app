import json
import os
from dotenv import load_dotenv
from datetime import datetime
from argparse import ArgumentParser

from agno.utils.log import logger
from agno.workflow import RunResponse

from exceptions.exceptions import WorkflowException
from models.report_results import ReportResultsTemp
from workflows.insiders_workflow_v2 import InsidersWorkflow

load_dotenv()


def main(company_name: str) -> None:
    workflow = InsidersWorkflow()

    try:
        response: RunResponse = workflow.run(company_name=company_name)
        logger.info("Workflow completed.")
    except WorkflowException as e:
        logger.error("Workflow error.")
        logger.error(str(e))
        return
    except Exception as e:
        logger.error("Unexpected error.")
        logger.error(str(e))
        return

    if response.content == "":
        return

    # Save the results to a file in ../results/v3 folder
    os.makedirs("results/v3", exist_ok=True)
    filename = f"{company_name.replace(' ', '_').lower()}_insiders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join("results/v3", filename)

    with open(filepath, "w") as f:
        content = response.content
        if isinstance(content, ReportResultsTemp):
            f.write(content.model_dump_json(indent=4))
        else:
            f.write(json.dump(content, indent=4))
        logger.info(f"Results saved to {filepath}.")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-c",
        "--company_name",
        type=str,
        required=True,
    )

    args = parser.parse_args()
    main(args.company_name)
