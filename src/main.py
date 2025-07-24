if __name__ == "__main__":

    from dotenv import load_dotenv

    load_dotenv()

    from workflows.insiders_workflow import InsidersWorkflow

    workflow = InsidersWorkflow()
    workflow.run(company_name="Leonardo S.p.A.")
