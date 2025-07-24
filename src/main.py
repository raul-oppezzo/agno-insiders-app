from dotenv import load_dotenv
from argparse import ArgumentParser
from workflows.insiders_workflow import InsidersWorkflow

if __name__ == "__main__":
    load_dotenv()

    parser = ArgumentParser(description="Run the insiders workflow.")
    parser.add_argument(
        "-company_name",
        type=str,
        description="Name of the company to process",
        required=True,
    )

    args = parser.parse_args()

    workflow = InsidersWorkflow()
    workflow.run(company_name=args.company_name)
    print(f"Workflow completed for company: {args.company_name}")