import os
import re
from datetime import datetime
from neo4j import GraphDatabase, Driver

from agno.utils.log import logger
from models.report_results import ReportResultsTemp


class DBDriver:
    _driver: Driver = None

    def __init__(self):
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        self._driver = GraphDatabase.driver(uri, auth=(username, password))

        self._driver.verify_connectivity()

    def close(self):
        if self._driver is not None:
            self._driver.session(database="neo4j").close()
            self._driver.close()

    def save_report_results(self, report_results: ReportResultsTemp) -> None:
        self._save_nodes(report_results.nodes)
        self._save_edges(report_results.edges)

    def _save_nodes(self, nodes) -> None:
        # group props per label because label cannot be parameterized in Cypher
        grouped: dict[str, list[dict]] = {}
        for n in nodes:
            if not n.id:
                logger.warning(f"Node without id, skipping: {n}")
                continue
            node_props = {"id": n.id}
            node_props.update(self._get_properties_dictionary(n))
            label = n.label or "Node"
            grouped.setdefault(label, []).append(node_props)

        for label, props in grouped.items():
            # sanitize label (allow only alnum and underscore)
            label_safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
            query = f"""
UNWIND $props AS properties
MERGE (n:{label_safe} {{id: properties.id}})
SET n = properties
"""
            self._driver.execute_query(query, {"props": props})

    def _save_edges(self, edges) -> None:
        # group edge creations by relationship type (type can't be parameterized)
        grouped: dict[str, list[dict]] = {}
        for e in edges:
            if not e.source or not e.dest:
                logger.warning(f"Edge without start or end node id, skipping: {e}")
                continue
            rel_props = self._get_properties_dictionary(e)
            item = {"source": e.source, "dest": e.dest, "props": rel_props}
            rel_type = e.type or "RELATED_TO"
            grouped.setdefault(rel_type, []).append(item)

        for rel_type, props in grouped.items():
            rel_safe = re.sub(r"[^A-Za-z0-9_]", "_", rel_type)
            query = f"""
UNWIND $props AS properties
MATCH (a {{id: properties.source}}), (b {{id: properties.dest}})
MERGE (a)-[r:{rel_safe}]->(b)
SET r = properties.props
"""
            self._driver.execute_query(query, {"props": props})

    def _get_properties_dictionary(self, node) -> dict:
        properties = {}
        for k, v in node.properties.items():
            # Skip empty values to not overwrite existing data with nulls
            if v is None or v == "":
                continue

            # Convert ISO date strings to date objects for specific fields
            # if k in ["dateOfBirth", "startDate", "from", "to"]:
            #    try:
            #        v_dt = datetime.fromisoformat(v)
            #        v = v_dt.date()
            #    # If error, keep original value
            #    except ValueError as e:
            #        v = v
            properties[k] = v
        return properties
