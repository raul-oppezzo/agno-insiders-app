from datetime import datetime
import os
from dotenv import load_dotenv
from argparse import ArgumentParser

from agno.utils.log import logger
from agno.workflow import RunResponse

from models.report_results import ReportResults
from workflows.insiders_workflow_v2 import InsidersWorkflow

load_dotenv()


def run_workflow(company_name: str) -> None:
    try:
        workflow = InsidersWorkflow()

        logger.info("Starting the insiders workflow...")
        response: RunResponse = workflow.run(company_name=company_name)

        if isinstance(response.content, ReportResults):
            logger.info("Workflow completed successfully.")
            
            # Save the results to a file in ../results/v2 folder
            os.makedirs("/results/v2", exist_ok=True)
            filename = f"{company_name.replace(' ', '_').lower()}_insiders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join("/results/v2", filename)
            
            with open(filepath, "w") as f:
                f.write(response.content.model_dump_json(indent=2, exclude_none=True))

            logger.info(f"Results saved to {filepath}.")
        else:
            logger.warning("Workflow failed.")
            print(response.content)
    except Exception as e:
        logger.error(f"Workflow failed with error: {str(e)}")
        exit(1)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-c",
        "--company_name",
        type=str,
        required=True,
    )

    args = parser.parse_args()
    run_workflow(args.company_name)
