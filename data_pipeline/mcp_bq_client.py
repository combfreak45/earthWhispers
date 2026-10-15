"""
BigQuery client for EarthWhisper's grounding queries.

The project spec frames data access as going through Google's managed BigQuery MCP
Server (https://bigquery.googleapis.com/mcp). This module provides that access via
the standard `google-cloud-bigquery` client, exposed behind the same
`BigQueryMCPClient.execute_query()` interface the agent tools expect
(`agent/tools/bq_mcp_client.py`). Keeping the interface stable means a real MCP
transport can be dropped in later without touching the callers.

Auth: uses Application Default Credentials. For local runs:
    gcloud auth application-default login
"""

import os
import logging
from typing import Any, Dict, List, Optional

from google.cloud import bigquery

logger = logging.getLogger("earthwhisper-bq-client")


class BigQueryMCPClient:
    """Thin wrapper over google-cloud-bigquery with an MCP-style execute_query()."""

    def __init__(self, project_id: Optional[str] = None, location: Optional[str] = None):
        self.project_id = project_id or os.getenv("PROJECT_ID")
        # Leave unset to let BigQuery auto-detect the dataset's location.
        # Override via BIGQUERY_LOCATION only if auto-detection ever fails.
        self.location = location or os.getenv("BIGQUERY_LOCATION") or None
        self._client: Optional[bigquery.Client] = None

    @property
    def client(self) -> bigquery.Client:
        """Lazily create the BigQuery client so import never requires credentials."""
        if self._client is None:
            self._client = bigquery.Client(project=self.project_id)
            logger.info("Initialized BigQuery client for project '%s'.", self.project_id)
        return self._client

    def execute_query(
        self,
        query: str,
        params: Optional[List[bigquery.ScalarQueryParameter]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run a SQL query and return rows as a list of plain dicts.

        `params` enables parameterized queries (preferred over string interpolation);
        callers may omit it for static SQL.
        """
        job_config = bigquery.QueryJobConfig(query_parameters=params or [])
        logger.debug("Executing BigQuery query:\n%s", query)
        job = self.client.query(query, job_config=job_config, location=self.location)
        rows = job.result()
        return [dict(row.items()) for row in rows]

    def insert_rows(self, table_id: str, rows: List[Dict[str, Any]]) -> None:
        """
        Append rows to a table via the streaming insert API.
        `table_id` is the fully-qualified `project.dataset.table`.
        Raises RuntimeError if BigQuery reports per-row errors.
        """
        errors = self.client.insert_rows_json(table_id, rows)
        if errors:
            raise RuntimeError(f"BigQuery insert into {table_id} failed: {errors}")
        logger.info("Inserted %d row(s) into %s.", len(rows), table_id)
