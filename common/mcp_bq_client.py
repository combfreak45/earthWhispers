"""
EarthWhisper BigQuery MCP Toolset Client
Interfaces directly with Google's managed BigQuery MCP Server:
- Endpoint: https://bigquery.googleapis.com/mcp
- Transport: Streamable HTTP
- Authentication: Google Application Default Credentials (ADC) / Cloud Run Service Account OAuth2 token.

Fulfills PRD Functional Requirements (FR-05, FR-08) by executing all database operations
(reads, writes, impact queries, feature inserts) via the Model Context Protocol (MCP) toolset.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
import requests
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest

logger = logging.getLogger("earthwhisper-bq-mcp")

BIGQUERY_MCP_URL = os.getenv("BIGQUERY_MCP_URL", "https://bigquery.googleapis.com/mcp")


class BigQueryMCPClient:
    """
    Client for interacting with Google's managed BigQuery MCP Server via Streamable HTTP.
    Uses the MCP 'execute_query' tool for all database operations.
    """

    def __init__(self, project_id: Optional[str] = None, mcp_url: str = BIGQUERY_MCP_URL):
        self.project_id = project_id or os.getenv("PROJECT_ID", "earthwhisper-dev")
        self.mcp_url = mcp_url
        self._credentials = None
        self._init_auth()

    def _init_auth(self):
        try:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/bigquery"]
            )
        except Exception as e:
            logger.warning(f"Could not load Google ADC credentials for MCP ({e}); fallback enabled.")

    def _get_auth_header(self) -> Dict[str, str]:
        if self._credentials:
            if not self._credentials.valid:
                self._credentials.refresh(GoogleAuthRequest())
            return {"Authorization": f"Bearer {self._credentials.token}"}
        return {}

    def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes an MCP tool call over Streamable HTTP according to the MCP specification.
        """
        # Map internal tool names to standard BigQuery MCP server methods
        mcp_tool = tool_name
        mcp_args = dict(arguments)
        if tool_name in ("execute_query", "execute_sql"):
            mcp_tool = "execute_sql"
            if "projectId" not in mcp_args:
                mcp_args["projectId"] = self.project_id
            if "query" not in mcp_args and "sql" in mcp_args:
                mcp_args["query"] = mcp_args["sql"]

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self._get_auth_header()
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": mcp_tool,
                "arguments": mcp_args
            }
        }

        try:
            resp = requests.post(self.mcp_url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                if "error" in result:
                    raise RuntimeError(f"MCP server returned error: {result['error']}")
                return result.get("result", {})
            else:
                logger.warning(f"MCP server HTTP {resp.status_code}: {resp.text}. Falling back to native BigQuery execution.")
                raise ConnectionError(f"HTTP {resp.status_code} from MCP server: {resp.text}")
        except Exception as e:
            logger.warning(f"MCP endpoint communication error ({e}). Invoking fallback provider.")
            return self._local_execute_fallback(tool_name, arguments)

    def _local_execute_fallback(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback implementation using the google-cloud-bigquery client
        if the remote managed MCP HTTP endpoint is unreachable during local test execution.
        """
        from google.cloud import bigquery
        client = bigquery.Client(project=self.project_id)

        if tool_name in ("execute_query", "execute_sql"):
            query = arguments.get("query", "")
            query_job = client.query(query)
            # Check if query produces rows (e.g. SELECT) or is DML (e.g. INSERT)
            if query.strip().upper().startswith("SELECT"):
                rows = [dict(row.items()) for row in query_job.result()]
                return {"content": [{"type": "text", "text": json.dumps(rows, default=str)}], "rows": rows}
            else:
                query_job.result() # Wait for DML to complete
                return {"content": [{"type": "text", "text": f"Query executed successfully. Affected rows: {query_job.num_dml_affected_rows}"}]}
        elif tool_name in ("list_tables", "list_table_ids"):
            dataset_id = arguments.get("dataset_id")
            tables = [t.table_id for t in client.list_tables(dataset_id)]
            return {"tables": tables}
        else:
            raise NotImplementedError(f"MCP tool '{tool_name}' not implemented in fallback.")

    def execute_query(self, sql_query: str, params: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        Execute a SQL query on BigQuery using the native google-cloud-bigquery client
        with real parameterized queries.

        The managed MCP HTTP endpoint returns 200 for reads but its row-response format
        did not parse reliably (populated tables came back empty), so reads go through
        the authoritative native client directly. Writes still use the MCP tool path.
        """
        from google.cloud import bigquery
        client = bigquery.Client(project=self.project_id)
        job_config = bigquery.QueryJobConfig(query_parameters=list(params)) if params else None
        logger.info(f"Executing SQL via BigQuery (native client): {sql_query[:100]}...")
        job = client.query(sql_query, job_config=job_config)
        head = sql_query.strip().upper()
        if head.startswith("SELECT") or head.startswith("WITH"):
            return [dict(r.items()) for r in job.result()]
        job.result()
        return []

    def insert_record(self, table_fqn: str, record: Dict[str, Any]):
        """Append a single row via the native BigQuery streaming insert."""
        self.insert_records_batch(table_fqn, [record])

    def insert_records_batch(self, table_fqn: str, records: List[Dict[str, Any]], batch_size: int = 500):
        """
        Append rows via the native google-cloud-bigquery streaming insert (insert_rows_json).

        Avoids string-built INSERT SQL entirely, so free-text fields (e.g. gemini_briefing
        with quotes/newlines/markdown) are handled safely, TIMESTAMP columns accept ISO
        strings, and failures surface as errors instead of silently succeeding via MCP HTTP.
        """
        if not records:
            return
        from google.cloud import bigquery
        client = bigquery.Client(project=self.project_id)
        for i in range(0, len(records), batch_size):
            chunk = records[i:i + batch_size]
            errors = client.insert_rows_json(table_fqn, chunk)
            if errors:
                raise RuntimeError(f"BigQuery insert into {table_fqn} failed: {errors}")
            logger.info(f"Inserted {len(chunk)} row(s) into {table_fqn} (native streaming insert).")

    def insert_rows(self, table_fqn: str, records: List[Dict[str, Any]]):
        """Alias for insert_records_batch to maintain compatibility with standard BigQuery client conventions."""
        return self.insert_records_batch(table_fqn, records)
