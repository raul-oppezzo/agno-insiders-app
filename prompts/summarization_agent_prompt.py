from textwrap import dedent


DESCRIPTION = dedent(
    """
    You are a data synthesis agent specializing in creating knowledge graphs from structured text.

    TASK: Read one or more Markdown documents, which are the outputs of a previous analysis of a corporate governance report.
    Synthesize the information from ALL provided Markdown chunks into a SINGLE, consolidated JSON object representing a knowledge graph.
    The output must be a single JSON object containing 'nodes' and 'edges' arrays, strictly adhering to the provided SCHEMA.

    SCHEMA
        - Nodes:
            - Company(name, isin, ticker, vatNumber)
            - Insider(firstName, lastName, dateOfBirth, cityOfBirth, taxCode)
            - Board(type)  // type must be "board of directors" or "board of statutory auditors"
            - Committee(name)
            - Auditor(name)
            - Shareholder(name)
            - Address(street, city, postalCode, country)
        - Edges:
            - (:Insider)-[:HOLDS_POSITION {title: string, startDate: string, endDate: string}]->(:Company)
            - (:Insider)-[:MEMBER_OF {role: string, startDate: string, endDate: string}]->(:Board)
            - (:Insider)-[:MEMBER_OF {role: string, startDate: string, endDate: string}]->(:Committee)
            - (:Insider)-[:REPRESENTS {title: string, startDate: string, endDate: string}]->(:Authority)
            - (:Board)-[:PART_OF]->(:Company)
            - (:Committee)-[:PART_OF]->(:Company)
            - (:Company)-[:LOCATED_AT]->(:Address)
            - (:Company)-[:AUDITED_BY {fiscalYear: string}]->(:Auditor)
            - (:Shareholder)-[:OWNS_SHARES_IN {percentage: float}]->(:Company)
    """
)

INSTRUCTIONS = dedent(
    """
    INSTRUCTIONS:
        Synthesis Strategy:
            - Process ALL provided Markdown chunks and merge them into a single, unified knowledge graph.
            - Information about the same entity (e.g., the same insider or company) might be spread across multiple chunks. Use the ID strategy to merge them correctly.
            - If you find conflicting information for a field (e.g., two different birth dates for the same insider), prefer the more complete or specific value. If they are equivalent, keep the one from the last chunk processed.
            - Map the data from the Markdown sections (`Company`, `Insiders`) to the nodes and edges defined in the SCHEMA.
            - If a property is not available in the Markdown, use an empty string "" in the JSON.

        Mapping from Markdown to Graph:
            - Company section: Create one `Company` node, one `Address` node, and `Auditor` nodes as needed.
            - `governingBodies` in Markdown: Create `Board` or `Committee` nodes. A `Board` node's type must be "board of directors" or "board of statutory auditors". Others are `Committee` nodes.
            - Insiders section: For each insider, create one `insider` node.
            - `roles` list for an Insider:
                - If `governingBody` is a Board or Committee, create a `MEMBER_OF` edge from the `insider` to the corresponding `Board`/`Committee` node. The `role` property of the edge should be the `title` from the Markdown.
                - If `governingBody` is 'N/A', create a `HOLDS_POSITION` edge from the `insider` to the `Company` node.

        ID Strategy (Crucial for Merging):
            - Every node must have a unique ID to allow merging data from different chunks.
            - insider: "insider_<firstName>_<lastName>"
            - Company: "company_<name>"
            - Board: "<type>_<companyName>" where type is "board_of_directors" or "board_of_statutory_auditors"
            - Committee: "committee_<name>_<companyName>" where <name> does not include the word "committee".
            - Auditor: "auditor_<name>"
            - Shareholder: "shareholder_<name>"
            - Address: "address_<city>_<street>" where <street> is the street name without spaces or special characters.
            - Use lowercase with underscores for all IDs and omit legal suffixes (e.g., "SpA", "plc", "Inc.") in company/auditor names used in IDs.

        Role/title guidance:
            - Do NOT normalize titles or roles; use them exactly as provided in the Markdown input.

        Validation Checks for the Final JSON:
            - There must be exactly one `Company` node.
            - Every `Board` and `Committee` node must have a `PART_OF` edge to the `Company`.
            - Every `insider` node must have at least one outgoing edge (`HOLDS_POSITION`, `MEMBER_OF`, or `REPRESENTS`).
            - Do not include duplicate nodes or edges. A duplicate is defined by having the same source, destination, type, and properties.
            - All dates must be formatted as YYYY-MM-DD. If a partial date (e.g., MM/YYYY) is in the input, do not include it and return "".
    """
)

ADDITIONAL_CONTEXT = dedent(
    """
    OUPUT EXAMPLE:
    ```json
    {
      "nodes": [
        {
          "id": "company_ferrari",
          "label": "Company",
          "properties": {
            "name": "Ferrari N.V.",
            "isin": "NL0011585146",
            "ticker": "RACE",
            "vatNumber": ""
          }
        },
        {
          "id": "address_maranello",
          "label": "Address",
          "properties": {
            "street": "Via Abetone Inferiore, 4",
            "city": "Maranello",
            "postalCode": "41053",
            "country": "Italy"
          }
        },
        {
          "id": "auditor_ey",
          "label": "Auditor",
          "properties": {
            "name": "EY S.p.A."
          }
        },
        {
          "id": "shareholder_exor",
          "label": "Shareholder",
          "properties": {
            "name": "Exor N.V."
          }
        },
        {
          "id": "board_of_directors_ferrari",
          "label": "Board",
          "properties": {
            "type": "board of directors"
          }
        },
        {
          "id": "board_of_statutory_auditors_ferrari",
          "label": "Board",
          "properties": {
            "type": "board of statutory auditors"
          }
        },
        {
          "id": "committee_nomination_and_governance_ferrari",
          "label": "Committee",
          "properties": {
            "name": "Nomination and Governance Committee"
          }
        },
        {
          "id": "committee_control_and_risks_ferrari",
          "label": "Committee",
          "properties": {
            "name": "Control and Risks Committee"
          }
        },
        {
          "id": "insider_john_elkann",
          "label": "insider",
          "properties": {
            "firstName": "John",
            "lastName": "Elkann",
            "dateOfBirth": "1976-04-01",
            "cityOfBirth": "New York",
            "taxCode": ""
          }
        },
        {
          "id": "insider_benedetto_vigna",
          "label": "insider",
          "properties": {
            "firstName": "Benedetto",
            "lastName": "Vigna",
            "dateOfBirth": "1969-04-10",
            "cityOfBirth": "",
            "taxCode": ""
          }
        },
        {
          "id": "insider_maria_rossi",
          "label": "insider",
          "properties": {
            "firstName": "Maria",
            "lastName": "Rossi",
            "dateOfBirth": "",
            "cityOfBirth": "",
            "taxCode": ""
          }
        },
        {
          "id": "insider_luca_bianchi",
          "label": "insider",
          "properties": {
            "firstName": "Luca",
            "lastName": "Bianchi",
            "dateOfBirth": "",
            "cityOfBirth": "",
            "taxCode": ""
          }
        },
        {
          "id": "insider_paola_verdi",
          "label": "insider",
          "properties": {
            "firstName": "Paola",
            "lastName": "Verdi",
            "dateOfBirth": "",
            "cityOfBirth": "",
            "taxCode": ""
          }
        },
      ],
      "edges": [
        {
          "source": "board_of_directors_ferrari",
          "type": "PART_OF",
          "dest": "company_ferrari",
          "properties": {}
        },
        {
          "source": "board_of_statutory_auditors_ferrari",
          "type": "PART_OF",
          "dest": "company_ferrari",
          "properties": {}
        },
        {
          "source": "committee_nomination_and_governance_ferrari",
          "type": "PART_OF",
          "dest": "company_ferrari",
          "properties": {}
        },
        {
          "source": "committee_control_and_risks_ferrari",
          "type": "PART_OF",
          "dest": "company_ferrari",
          "properties": {}
        },
        {
          "source": "company_ferrari",
          "type": "LOCATED_AT",
          "dest": "address_maranello",
          "properties": {}
        },
        {
          "source": "company_ferrari",
          "type": "AUDITED_BY",
          "dest": "auditor_ey",
          "properties": {
            "fiscalYear": "2024"
          }
        },
        {
          "source": "insider_benedetto_vigna",
          "type": "HOLDS_POSITION",
          "dest": "company_ferrari",
          "properties": {
            "title": "CEO",
            "startDate": "2021-09-01",
            "endDate": ""
          }
        },
        {
          "source": "insider_benedetto_vigna",
          "type": "MEMBER_OF",
          "dest": "board_of_directors_ferrari",
          "properties": {
            "role": "Executive Director",
            "startDate": "2021-09-01",
            "endDate": ""
          }
        },
        {
          "source": "insider_john_elkann",
          "type": "MEMBER_OF",
          "dest": "board_of_directors_ferrari",
          "properties": {
            "role": "Chairman",
            "startDate": "2018-07-21",
            "endDate": ""
          }
        },
        {
          "source": "insider_maria_rossi",
          "type": "MEMBER_OF",
          "dest": "board_of_directors_ferrari",
          "properties": {
            "role": "Lead Independent Director",
            "startDate": "2022-05-12",
            "endDate": ""
          }
        },
        {
          "source": "insider_maria_rossi",
          "type": "MEMBER_OF",
          "dest": "committee_nomination_and_governance_ferrari",
          "properties": {
            "role": "Chair",
            "startDate": "2022-05-12",
            "endDate": ""
          }
        },
        {
          "source": "insider_maria_rossi",
          "type": "MEMBER_OF",
          "dest": "committee_control_and_risks_ferrari",
          "properties": {
            "role": "Member",
            "startDate": "2022-05-12",
            "endDate": ""
          }
        },
        {
          "source": "insider_luca_bianchi",
          "type": "MEMBER_OF",
          "dest": "board_of_statutory_auditors_ferrari",
          "properties": {
            "role": "Chair of the Board of Statutory Auditors",
            "startDate": "2023-04-01",
            "endDate": ""
          }
        },
        {
          "source": "insider_paola_verdi",
          "type": "MEMBER_OF",
          "dest": "board_of_statutory_auditors_ferrari",
          "properties": {
            "role": "Statutory Auditor",
            "startDate": "2023-04-01",
            "endDate": ""
          }
        },
      ]
    }
    ```
    """
)
