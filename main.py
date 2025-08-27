import json
import os
from dotenv import load_dotenv
from datetime import datetime
from argparse import ArgumentParser

from agno.utils.log import logger
from agno.workflow import RunResponse

from models.report_results import ReportResults
from workflows.insiders_workflow_v2 import InsidersWorkflow

load_dotenv()


def main(company_name: str) -> None:
    workflow = InsidersWorkflow()

    try:
        response: RunResponse = workflow.run(company_name=company_name)
    except Exception as e:
        logger.error("Unexpected error from workflow.")
        logger.error(str(e))
        return

    logger.info("Workflow completed successfully.")

    # Save the results to a file in ../results/v2 folder
    os.makedirs("results/v3", exist_ok=True)
    filename = f"{company_name.replace(' ', '_').lower()}_insiders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join("results/v3", filename)

    with open(filepath, "w") as f:
        f.write(json.dumps(response.content, indent=4))

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
