if __name__ == "__main__":

    from dotenv import load_dotenv

    load_dotenv()

    from workflows.insiders_workflow import InsidersWorkflow

    from agno.utils.pprint import pprint_run_response

    workflow = InsidersWorkflow()
    response = workflow.run(company_name="Leonardo S.p.A.")

    pprint_run_response(response, markdown=True, show_time=True)
