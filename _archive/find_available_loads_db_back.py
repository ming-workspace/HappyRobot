# find_available_loads.py
import os
import json
import logging
import psycopg2
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LoadServiceDB(BaseHTTPRequestHandler):
    ROUTE = '/loads_db'

    def _db_connection(self):
        return psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST', 'postgres'),
            port=os.getenv('DB_PORT', '5432')
        )

    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

    def _authenticate(self):
        api_key = self.headers.get('X-API-Key')
        valid_keys = os.getenv("MING_HAPPYROBOT_API_KEYS", "").split(',')
        if not api_key or api_key not in valid_keys:
            self._send_error(401, "Invalid or missing API key")
            return False
        return True

    def _send_response(self, data, status=200):
        self._set_headers(status)
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, status, message, details=None):
        error = {
            "error": message,
            "status": status,
            "path": self.path
        }
        if details:
            error["details"] = details
        self._send_response(error, status)

    def _build_query(self, params):
        base_query = """
            SELECT reference_number, origin, destination, 
                   equipment_type, rate, commodity 
            FROM loads 
            WHERE 1=1
        """
        conditions = []
        values = []

        if 'reference_number' in params:
            ref_nums = params['reference_number'][0].split(',')
            conditions.append(f"reference_number = ANY(%s)")
            values.append(ref_nums)

        if 'origin' in params:
            conditions.append("origin = %s")
            values.append(params['origin'][0].upper())

        if 'destination' in params:
            conditions.append("destination = %s")
            values.append(params['destination'][0].upper())

        if 'equipment_type' in params:
            conditions.append("equipment_type ILIKE %s")
            values.append(f"%{params['equipment_type'][0].upper()}%")

        return (
            base_query + " AND " + " AND ".join(conditions) if conditions else base_query,
            values
        )

    def _search_loads(self, params):
        try:
            query, values = self._build_query(params)
            with self._db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, values)
                    columns = [desc[0] for desc in cur.description]
                    return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Database error: {str(e)}")
            raise

    def do_GET(self):
        parsed_path = urlparse(self.path)
        clean_path = parsed_path.path.rstrip('/')

        if clean_path != self.ROUTE:
            return self._send_error(404, f"Invalid endpoint: {parsed_path.path}")

        if not self._authenticate():
            return

        try:
            params = parse_qs(parsed_path.query)
            results = self._search_loads(params)

            response = {
                "count": len(results),
                "results": results
            }

            if not results:
                response["message"] = "No matching loads found"
                self._send_response(response, 404)
            else:
                self._send_response(response)

        except Exception as e:
            logger.error(f"Processing error: {str(e)}", exc_info=True)
            self._send_error(500, "Internal server error")


def run(port=8002):
    server = HTTPServer(('', port), LoadServiceDB)
    logger.info(f"DB Load Service running on port {port}")
    server.serve_forever()


if __name__ == '__main__':
    run()