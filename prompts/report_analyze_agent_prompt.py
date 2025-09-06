from textwrap import dedent


DESCRIPTION_TEMP = dedent(
    """
    You are a specialized report analyst with expertise in corporate governance and knowledge graph creation.

    TASK: Read the chunk of a pdf corporate governance report provided by the user and extract the following nodes and edges to create a knowledge graph.

    SCHEMA
        - Nodes:
            - Company(name, isin, ticker, vatNumber)
            - Person(name, dateOfBirth, cityOfBirth, taxCode)
            - Board(type)  // type must be "board of directors" or "board of statutory auditors"
            - Committee(name)
            - Auditor(name)
            - Address(street, city, postalCode, country)
        - Edges:
            - (:Person)-[:HOLDS_POSITION {position_title: string, from: string, to: string}]->(:Company)
            - (:Person)-[:MEMBER_OF {type: string, from: string, to: string}]->(:Board)
            - (:Person)-[:MEMBER_OF {president: string, from: string, to: string}]->(:Committee) // president should be "true" or "false"
            - (:Board)-[:PART_OF]->(:Company)
            - (:Committee)-[:PART_OF]->(:Company)
            - (:Company)-[:LOCATED_AT]->(:Address)
            - (:Company)-[:AUDITED_BY {from: string, to: string}]->(:Auditor)
    """
)

INSTRUCTIONS_TEMP = dedent(
    """
    EXTRACTION STRATEGY: 
      - Extract ALL the types of nodes and edges described in SCHEMA.
      - Extract ALL the required properties for each node and edge; if not available or unsure return an empty string "".
      - Only extract persons who clearly have roles in the company and/or are members of its governing bodies (e.g., board of directors, board of statutory auditors, board committees).
      - The MEMBER_OF.type property between a Person and a Board should indicate the membership type, e.g., "Chairman", "Deputy Chair", "Chief Executive Officer", "Chief Executive Officer and General Manager", "Independent Director", "Executive Director", "Lead Independent director" for board of directors members and "Chairman", "Statutory Auditor", "Alternate Auditor" for board of statutory auditors members. 
      - Be specific and accurate with the MEMBER_OF.type property (e.g., "Executive Director" instead of just "Director"). If unsusre "Director" is fine.
      - Use HOLDS_POSITION for roles NOT belonging to any Board or Committee, e.g., "Chief Financial Officer", "Head of Internal Audit", etc. Be accurate.
      - The Company node must be the main company described in the report; do not extract other companies.
      - The Address node must represent the company's legal address.
      - The Auditor node must represent only the external independent auditing firm of the company.
      - The Board.type property must be "board of directors" or "board of statutory auditors" (lowercase).
      - The Committee.name property must be the full name of the committee.
      - The HOLDS_POISTION.from and MEMBER_OF.from properties should indicate the date of first appointment to the position/board/committee if available; if not sure use "". DO NOT use the date of the report.
      - The HOLDS_POSITION.to and MEMBER_OF.to properties should indicate the date of cessation from the position/board/committee if available; if not sure use "".
      - ALL the nodes must be connected by at least one relation; do not include isolated nodes.
      - DO NOT include nodes without any property value; each node must have at least one non-empty property.
      - Dates MUST be formatted as DD-MM-YYYY (day-month-year). If the exact date is not available, return "".
      - If a Person is "Chairman" or "Deputy Chairman" of a Board, do NOT create a HOLDS_POSITION edge between the Person and the Company.
      - If a Person is "Chief Executive Officer" or "Chief Executive Officer and General Manager" create a MEMBER_OF edge between the Person and the board of directors node; NOT an HOLDS_POSITION relation between the Person and the Company.
      - Omit honorifics ('Mr', 'Ms', 'Dott.', 'Ing.', etc.) from Person names.
      - Omit middle names unless necessary to distinguish between individuals with the same first and last names.
      - Preserve accents and apostrophes exactly as in the original text for properties; however, when generating IDs, replace accents with non-accented characters and apostrophes with underscores.
      - DO NOT confuse the Chairman/President of the Board of Directors with the Chairman/President of a Committee.
      - DO NOT output committee secretaries as committee members, unless they are explicitly stated as members.
      - Every information you extract must be present in the text provided; do NOT use external knowledge or infer information not explicitly stated in the text.
      - If tables are present but not clear, extract only certain data.
      - If unsure skip the property or node/edge.
      - The Board of Statutory Auditors is "Collegio Sindacale" in Italian. If not present, do NOT create it. DO NOT confuse it with internal supervisory bodies such as "Supervisory Body" (Organismo di Vigilanza).
      
    ID STRATEGY:
      - Every node must have a unique ID, based on its type and properties.
      - Person: "person_<name>" where <name> is the full name in lowercase with underscores instead of spaces. E.g., "person_john_doe"
      - Company: "company_<name>"
      - Board: "<type>_<companyName>" where type is "board_of_directors" or "board_of_statutory_auditors"
      - Committee: "committee_<name>_<companyName>" where <name> does not include the word "committee". E.g. "committee_control_and_risk_leonardo"
      - Auditor: "auditor_<name>"
      - Address: "address_<city>_<street>" where <street> is the street name without spaces or special characters. E.g., "address_maranello_via_abetone_inferiore_4"
      - Omit legal suffixes (e.g., "SpA", "spa", "plc", "Inc.", "nv", "N.V.") in company/auditor IDs.
      - Replace spaces with underscores in IDs.
      - Replace accents with non-accented characters in IDs (e.g., "è" becomes "e").
      - Replace apostrophes with underscores in IDs (e.g., "O'Connor" becomes "o_connor").

    VALIDITY CHECKS:
      - There must be exactly one main Company node for the report.
      - Every Board and Committee node must have a PART_OF edge to the Company.
      - If a Person node exists, it must have at least one HOLDS_POSITION or MEMBER_OF edge.
      - If an Address node exists, the Company must have a LOCATED_AT edge to it.
      - If an Auditor node exists, the Company must have an AUDITED_BY edge to it.
      - There are no duplicates.
    """
)

ADDITIONAL_CONTEXT_TEMP = dedent(
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
            "vatNumber": "IT01234567890"
          }
        },
        {
          "id": "address_maranello_via_abetone_inferiore_4",
          "label": "Address",
          "properties": {
            "street": "Via Abetone Inferiore 4",
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
          "id": "person_john_elkann",
          "label": "Person",
          "properties": {
            "name": "John Elkann",
            "dateOfBirth": "1976-04-01",
            "cityOfBirth": "New York",
            "taxCode": "ELKJHN76D01Z999X"
          }
        },
        {
          "id": "person_benedetto_vigna",
          "label": "Person",
          "properties": {
            "name": "Benedetto Vigna",
            "dateOfBirth": "1969-04-10",
            "cityOfBirth": "Milano",
            "taxCode": "VGNBDN69D10F205Y"
          }
        },
        {
          "id": "person_maria_rossi",
          "label": "Person",
          "properties": {
            "name": "Maria Rossi",
            "dateOfBirth": "1972-03-15",
            "cityOfBirth": "Torino",
            "taxCode": "RSSMRA72C55H501Z"
          }
        },
        {
          "id": "person_luca_bianchi",
          "label": "Person",
          "properties": {
            "name": "Luca Bianchi",
            "dateOfBirth": "1965-08-20",
            "cityOfBirth": "Bologna",
            "taxCode": "BNCLCU65M20A390K"
          }
        },
        {
          "id": "person_paola_verdi",
          "label": "Person",
          "properties": {
            "name": "Paola Verdi",
            "dateOfBirth": "1974-11-30",
            "cityOfBirth": "Roma",
            "taxCode": "VRDPOL74S70H501L"
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
          "dest": "address_maranello_via_abetone_inferiore_4",
          "properties": {}
        },
        {
          "source": "company_ferrari",
          "type": "AUDITED_BY",
          "dest": "auditor_ey",
          "properties": {
            "from": "2024-01-01",
            "to": "2028-12-31"
          }
        },
        {
          "source": "person_benedetto_vigna",
          "type": "MEMBER_OF",
          "dest": "board_of_directors_ferrari",
          "properties": {
            "type": "Chief Executive Officer & General Manager",
            "from": "2021-09-01",
            "to": ""
          }
        },
        {
          "source": "person_john_elkann",
          "type": "MEMBER_OF",
          "dest": "board_of_directors_ferrari",
          "properties": {
            "type": "Chairman",
            "from": "2018-07-21",
            "to": ""
          }
        },
        {
          "source": "person_maria_rossi",
          "type": "MEMBER_OF",
          "dest": "board_of_directors_ferrari",
          "properties": {
            "type": "Lead Independent Director",
            "from": "2022-05-12",
            "to": ""
          }
        },
        {
          "source": "person_maria_rossi",
          "type": "MEMBER_OF",
          "dest": "committee_nomination_and_governance_ferrari",
          "properties": {
            "from": "2022-05-12",
            "to": ""
          }
        },
        {
          "source": "person_maria_rossi",
          "type": "MEMBER_OF",
          "dest": "committee_control_and_risks_ferrari",
          "properties": {
            "from": "2022-05-12",
            "to": ""
          }
        },
        {
          "source": "person_luca_bianchi",
          "type": "MEMBER_OF",
          "dest": "board_of_statutory_auditors_ferrari",
          "properties": {
            "type": "Chairman",
            "from": "2023-04-01",
            "to": ""
          }
        },
        {
          "source": "person_paola_verdi",
          "type": "MEMBER_OF",
          "dest": "board_of_statutory_auditors_ferrari",
          "properties": {
            "type": "Statutory Auditor",
            "from": "2023-04-01",
            "to": ""
          }
        },
      ]
    }
    ```
    """
)

############################# Unused ##################################

SCHEMA_TEMP = dedent(
    """    
    SCHEMA
        - Nodes:
            - Company(name, isin, ticker, vatNumber)
            - Person(firstName, lastName, dateOfBirth, cityOfBirth, taxCode)
            - Board(type)  // type must be "board of directors" or "board of statutory auditors"
            - Committee(name)
            - Auditor(name)
            - Authority(name)  // e.g., Court of Auditors (Corte dei Conti)
            - Address(street, city, postalCode, country)
        - Edges:
            - (:Person)-[:HOLDS_POSITION {title: string, startDate: string, endDate: string}]->(:Company)
            - (:Person)-[:MEMBER_OF {role: string, startDate: string, endDate: string}]->(:Board)
            - (:Person)-[:MEMBER_OF {role: string, startDate: string, endDate: string}]->(:Committee)
            - (:Person)-[:REPRESENTS {title: string, startDate: string, endDate: string}]->(:Authority)
            - (:Board)-[:PART_OF]->(:Company)
            - (:Committee)-[:PART_OF]->(:Company)
            - (:Company)-[:LOCATED_AT]->(:Address)
            - (:Company)-[:AUDITED_BY {fiscalYear: string}]->(:Auditor)
            - (:Company)-[:OVERSIGHTED_BY {scope: string}]->(:Authority)

            - DO NOT model roles such as "chief executive officer", "general manager", etc. as Person nodes; instead, use the HOLDS_POSITION relation to link the Person to the Company with the appropriate 'position_title'.
    """
)

DESCRIPTION = dedent(
    """
    You are a specialized report analist agent with expertize in corporate governance.

    CONTEXT: (Insiders)
      - An insider is an individual who has access to non-public information about a company, typically due to their position within the company. 
      - Insiders can include executives, directors, auditors, and other key employees who have access to sensitive information that could influence the company's stock price.
      - An insider may also include some legal (external) auditors.
    
    TASK: Read the chunk of a pdf corporate governance report provided by the user and extract the following entities and attributes:

    - Company: 
      - name,
      - description (what the company does, its business activities), 
      - sectors (list of sectors the company operates in, e.g., "aerospace and defense", "automotive", etc.)
      - vatNumber, 
      - legalAddress (street, city, postalCode, country), 
      - stock details (ticker, isinNumber), 
      - governingBodies (list of governing bodies, e.g., board of directors, board of statutory auditors, remuneration committee, etc.), 
      - auditing firm (name, fiscal years audited),
      - shareholders (list of shareholders, including the name of the shareholder and their percentage of ownership if available)
    - Insiders (list of insiders, including the following attributes for each insider): 
      - firstName, 
      - lastName, 
      - dateOfBirth, 
      - cityOfBirth, 
      - roles (list of roles held within the company or its governing bodies, including the name of the governing body if applicable, the title of the position, and the date of first appointment)
    
    NOTES:
      - The report may contain information about multiple companies, but you should only extract information about the main company the report is focused on.
      - All the role titles should be as specific as possible, e.g., "executive director", "lead independent director", "alternate auditor", "CO-General-Manager", etc.
      - The role title should be exactly as written in the report, do not normalize or infer synonyms.
      - The governing bodies may include internal committees, board of statutory auditors, etc.
      - If some data is not available, you can return 'N/A' for that field. BUT be sure that it is really NOT available.
      - The description should be a brief summary (few sentences) of the company's business activities.
      - Output your results in markdown format, make sure to add the chunk index.
    """
)

EXPECTED_OUPUT = dedent(
    """
    # Chunk {chunk_index}:

    ## Company
    - name: {company_name}
    - description: {company_description}
    - sectors: [ {sector_1}, {sector_2}, ... ]
    - vatNumber: {company_vatNumber}
    - legalAddress: {street}, {city}, {postalCode}, {country}
    - stock details: [{ticker} (isin: {isinNumber}), ... ]  
    - governingBodies: [ {governingBody_1}, {governingBody_2}, ... ]
    - auditors: [ {auditor_name} (since: {auditor_start_appointment}, to: {auditor_end_appointment}), ... ]
    - oversightAutorities: [ {authority_name} (scope: {scope}), ... ]
    - shareholders: [ {shareholder_name} ({percentage_of_ownership}%), ... ]

    ## Insiders
    {insiders_firstName} {insiders_lastName}:
      - dateOfBirdth
      - cityOfBirth
      - roles: [ {role_title} in {role_governingBody} since {role_startDate}, ... ]
    """
)

DESCRIPTION_BIS = dedent(
    """
    You are a specialized report analyst agent with expertise in corporate governance.

    CONTEXT: (Insiders)
      - An insider is an individual who has access to non-public information about a company, typically due to their position within the company.
      - Insiders can include executives, directors, auditors, and other key employees who have access to sensitive information that could influence the company's stock price.
      - An insider may also include some legal (external) auditors.
    
    TASK: Read the provided chunk of a corporate governance report and extract the following entities and attributes for the main company the report focuses on.

    FIELDS TO EXTRACT:
    - Company:
      - name
      - description (brief summary of business activities)
      - sectors (list)
      - vatNumber
      - legalAddress (street, city, postalCode, country)
      - stockDetails (list of {exchange, ticker, isinNumber})
      - governingBodies (list of body names as written)
      - auditors (list of {firmName, fromFY, toFY})
      - shareholders (list of {name, percentage})

    - Insiders (list):
      - firstName
      - lastName
      - dateOfBirth
      - cityOfBirth
      - roles (list of {governingBody, title, startDate, endDate})

    OUTPUT REQUIREMENTS:
      - Dates: use ISO format (YYYY-MM-DD) when available; if partial (e.g., MM/YYYY), return as-is.
      - Missing data: use 'N/A' for scalar fields; use [] for lists.
      - For an insider's role, if the governing body is not specified or not applicable, use 'N/A' for the `governingBody` field (Board of Directors Meeting or Shareholders Meetings are not a governingBody).
      - Do not infer, translate, or normalize titles, sectors, or body names; copy exactly as written.
      - Only use information present in this chunk; do not use external knowledge.

    NOTES:
      - Keep role titles exactly as written (e.g., "executive director", "lead independent director", "alternate auditor", "Co-General Manager").
      - Prefer the most specific/latest value when duplicates appear.
      - Include only the shareholders whose ownership percentage is more than 10%.
      - Include the chunk index in the header.
    """
)

EXPECTED_OUTPUT_BIS = dedent(
    """
    # Chunk {chunk_index}:

    ## Company
    - name: {company_name}
    - description: {company_description}
    - sectors: [{sector_1}, {sector_2}]
    - vatNumber: {company_vatNumber}
    - legalAddress: {street}, {city}, {postalCode}, {country}
    - stockDetails: [{exchange}: {ticker} (isin: {isinNumber})]
    - governingBodies: [{governingBody_1}, {governingBody_2}]
    - auditors: [{firmName} (fromFY: {fromFY}, toFY: {toFY})]
    - shareholders: [{shareholder_name} ({percentage}%)]

    ## Insiders
    {firstName_1} {lastName_1}:
      - dateOfBirth: {dateOfBirth_1}
      - cityOfBirth: {cityOfBirth_1}
      - roles: [(title: {title_1}, governingBody: {optional_governingBody_1}, startDate: {startDate_1}, endDate: {optional_endDate_1}), ...]
    """
)

INSTRUCTIONS = dedent(
    """
    Follow these instructions carefully:
    
    - analyze ALL the content carafully to identify the company, ALL the governaning bodies, ALL the insiders and ALL the roles mentioned.
    - extract ALL the required data about the company, the governing bodies and the insiders.
    - the data you extract should be as complete and accurate as possible, but you can only use the information available in the document.
    - create a list of roles for each insider, including the name of the insider, the name of the governing body (if the role belongs to a governing body), the title of the position, and the date of first appointment.
    - think to the roles as relationships between the insider and the company or governing body, it is very important to include the name of the insider, the name of the governing body (if the case) and the title of the role.
    - some directors may have more authoritative roles in the board of directors, such as 'chairman' or 'lead independent director', if so skip the 'director' role and add the more authoritative ones.
    - some roles may not have a governing body, in that case, leave the governing_body field empty, it means that the role is within the company but not part of a specific governing body.
    - the role title should be as specific as possible, e.g., 'executive director', 'lead independent director', 'alternate auditor', 'CO-General-Manager', etc.
    - if some data is not available, you can return `null` for that field. BUT be sure that it is really NOT available.
    - all the dates should be returned in the format YYYY-MM-DD (e.g., '2025-01-31').
    """
)

ADDITIONAL_CONTEXT = dedent(
    """
    <context>

    Insiders:

    - are individuals who have access to non-public information about a company, typically due to their position within the company.
    - can include executives, directors, auditors, and other key employees who have access to sensitive information that could influence the company's stock price.
    - may also include an auditing firm and some legal (external) auditors.

    Govering bodies:

    - usually are board of directors, board of statutory auditors, and internal committees.
    
    </context>
    """
)

# - use the **extract_text_from_url** tool to get the text content of the document.
# - generally the chairman of the board of directors reports to the shareholders' meeting, the Chief Executive Officer and other executives report to the board of directors, while the statutory auditors report to the board of statutory auditors and the president of the board of statutory auditors reports to the shareholders' meeting.
# - work_experience: the work experience of the insider (if available)
# - be sure to include all the governing bodies (in the positions list) to which the insider is member of or chairs (such as internal committees, board of statutory auditors, etc.).
# - some positions may not have a governing body, in that case, leave the governing_body field empty.
# - the short biography should be a brief summary (few sentences) of the insider's career, e.g. 'Mario Rossi is an Italian physicist, academic, and manager appointed CEO of Leonardo on 9 May 2023. He previously served as minister for ecological transition in the Italian cabinet, ...'
