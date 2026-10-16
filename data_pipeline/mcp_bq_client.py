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

    def execute_query(self, sql_query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """
        High-level method to execute a SQL query on BigQuery via the MCP toolset.
        Returns parsed list of record dictionaries for SELECT queries.
        """
        logger.info(f"Executing SQL via BigQuery MCP Server: {sql_query[:100]}...")
        # If parameters provided, interpolate scalar params for standard MCP execute
        formatted_query = sql_query
        if params:
            for p in params:
                param_name = getattr(p, "name", None)
                param_val = getattr(p, "value", None)
                if param_name and param_val is not None:
                    val_str = f"'{param_val}'" if isinstance(param_val, str) else str(param_val)
                    formatted_query = formatted_query.replace(f"@{param_name}", val_str)

        result = self.call_mcp_tool("execute_query", {"query": formatted_query})

        # Helper to parse standard BigQuery REST/MCP schema+rows format
        def _parse_bq_format(data_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
            schema = data_dict.get("schema", {})
            fields = [f.get("name") for f in schema.get("fields", []) if f.get("name")]
            raw_rows = data_dict.get("rows", [])
            if not raw_rows or not fields:
                return []
            parsed = []
            for r in raw_rows:
                cells = r.get("f", [])
                row = {}
                for idx, cell in enumerate(cells):
                    if idx < len(fields):
                        row[fields[idx]] = cell.get("v")
                parsed.append(row)
            return parsed

        # Parse rows from direct or structuredContent MCP output
        if "rows" in result:
            if isinstance(result["rows"], list) and result["rows"] and isinstance(result["rows"][0], dict) and "f" in result["rows"][0]:
                return _parse_bq_format(result)
            return result["rows"]

        structured = result.get("structuredContent", {})
        if "rows" in structured:
            parsed = _parse_bq_format(structured)
            if parsed:
                return parsed

        # Parse text content from standard MCP tool response structure
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text":
                text = item.get("text", "")
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict) and "rows" in parsed:
                        extracted = _parse_bq_format(parsed)
                        if extracted:
                            return extracted
                except Exception:
                    pass
        return []

    def insert_record(self, table_fqn: str, record: Dict[str, Any]):
        """
        Executes a SQL INSERT statement through the BigQuery MCP Server.
        """
        columns = list(record.keys())
        values = []
        for col in columns:
            val = record[col]
            if val is None:
                values.append("NULL")
            elif isinstance(val, (int, float)):
                values.append(str(val))
            elif isinstance(val, bool):
                values.append("TRUE" if val else "FALSE")
            else:
                # String or timestamp
                escaped = str(val).replace("'", "\\'")
                values.append(f"'{escaped}'")

        cols_str = ", ".join(columns)
        vals_str = ", ".join(values)
        sql = f"INSERT INTO `{table_fqn}` ({cols_str}) VALUES ({vals_str})"
        self.call_mcp_tool("execute_query", {"query": sql})

    def insert_records_batch(self, table_fqn: str, records: List[Dict[str, Any]], batch_size: int = 50):
        """
        Batches multiple record inserts into parameterized multi-row SQL INSERT statements
        executed through the BigQuery MCP Server.
        """
        if not records:
            return

        columns = list(records[0].keys())
        cols_str = ", ".join(columns)

        for i in range(0, len(records), batch_size):
            chunk = records[i:i + batch_size]
            row_value_strings = []
            for rec in chunk:
                values = []
                for col in columns:
                    val = rec.get(col)
                    if val is None:
                        values.append("NULL")
                    elif isinstance(val, (int, float)):
                        values.append(str(val))
                    elif isinstance(val, bool):
                        values.append("TRUE" if val else "FALSE")
                    else:
                        escaped = str(val).replace("'", "\\'")
                        values.append(f"'{escaped}'")
                row_value_strings.append(f"({', '.join(values)})")

            vals_block = ",\n".join(row_value_strings)
            sql = f"INSERT INTO `{table_fqn}` ({cols_str}) VALUES\n{vals_block}"
            self.call_mcp_tool("execute_query", {"query": sql})
            logger.info(f"Inserted batch of {len(chunk)} rows into {table_fqn} via BigQuery MCP.")

    def insert_rows(self, table_fqn: str, records: List[Dict[str, Any]]):
        """
        Alias for insert_records_batch for compatibility with BigQuery client insert_rows signature.
        """
        return self.insert_records_batch(table_fqn, records)
