"""
EarthWhisper BigQuery MCP Toolset Client (Canonical Shared Library)
Interfaces with BigQuery:
- Protocol: Model Context Protocol (MCP) toolset via Streamable HTTP (https://bigquery.googleapis.com/mcp)
- Queries: Deterministic, parameterized execution using google-cloud-bigquery client
- Streaming Inserts: Native insert_rows_json API for robust free-text / markdown audit logging
- Authentication: Google Application Default Credentials (ADC) / Cloud Run Service Account OAuth2 token.

Fulfills PRD Functional Requirements (FR-05, FR-08) as the single source of truth for database operations.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
import requests
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest

logger = logging.getLogger("earthwhisper-bq-mcp")
logger.setLevel(logging.INFO)

BIGQUERY_MCP_URL = os.getenv("BIGQUERY_MCP_URL", "https://bigquery.googleapis.com/mcp")


def _resolve_project_id() -> str:
    """Resolve active Google Cloud Project ID dynamically from environment or ADC."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    for var in ("PROJECT_ID", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT"):
        val = os.getenv(var)
        if val and val.strip():
            return val.strip()
    try:
        _, auth_project = google.auth.default()
        if auth_project and auth_project.strip():
            return auth_project.strip()
    except Exception:
        pass
    return os.getenv("DEFAULT_GCP_PROJECT", "your-google-cloud-project-id")


class BigQueryMCPClient:
    """
    Client for interacting with BigQuery via the Model Context Protocol (MCP) toolset
    and Google Cloud BigQuery APIs.
    """

    def __init__(self, project_id: Optional[str] = None, mcp_url: str = BIGQUERY_MCP_URL):
        self.project_id = project_id or _resolve_project_id()
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
                res_obj = result.get("result", {})
                if res_obj.get("isError"):
                    err_texts = [c.get("text", "") for c in res_obj.get("content", []) if c.get("type") == "text"]
                    err_msg = " ".join(err_texts) or "Unknown MCP error"
                    raise RuntimeError(f"MCP server returned tool error: {err_msg}")
                return res_obj
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
            if query.strip().upper().startswith("SELECT") or query.strip().upper().startswith("WITH"):
                rows = [dict(row.items()) for row in query_job.result()]
                return {"content": [{"type": "text", "text": json.dumps(rows, default=str)}], "rows": rows}
            else:
                query_job.result()
                return {"content": [{"type": "text", "text": f"Query executed successfully. Affected rows: {query_job.num_dml_affected_rows}"}], "affected_rows": query_job.num_dml_affected_rows}
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
        Append rows via native google-cloud-bigquery streaming insert (insert_rows_json).
        Avoids SQL string concatenation, handles free-text markdown, quotes, and newlines safely.
        """
        if not records:
            return
        from google.cloud import bigquery
        client = bigquery.Client(project=self.project_id)
        clean_table = table_fqn.strip("`")
        for i in range(0, len(records), batch_size):
            chunk = records[i:i + batch_size]
            errors = client.insert_rows_json(clean_table, chunk)
            if errors:
                raise RuntimeError(f"BigQuery insert into {clean_table} failed: {errors}")
            logger.info(f"Inserted {len(chunk)} row(s) into {clean_table} (native streaming insert).")

    def insert_rows(self, table_fqn: str, records: List[Dict[str, Any]]):
        """Alias for insert_records_batch to maintain compatibility with standard BigQuery client conventions."""
        return self.insert_records_batch(table_fqn, records)
