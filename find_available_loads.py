# find_available_loads.py
import os
import json
import logging
import psycopg2
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


class LoadService(BaseHTTPRequestHandler):
    ROUTE = '/loads'

    def _db_connection(self):
        try:
            return psycopg2.connect(
                dbname=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                host=os.getenv('DB_HOST', 'postgres'),
                port=os.getenv('DB_PORT', '5432'),
                connect_timeout=5
            )
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {str(e)}")
            raise

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
        self.wfile.write(json.dumps(data, cls=DecimalEncoder).encode())

    def _send_error(self, status, message, details=None):
        error = {"error": message, "status": status, "path": self.path}
        if details: error["details"] = details
        self._send_response(error, status)

    def _get_reference_number_from_path(self, path):
        path_parts = path.strip('/').split('/')
        if len(path_parts) == 2 and path_parts[0] == 'loads':
            return path_parts[1].upper()
        return None

    def _handle_reference_number_request(self, reference_number):
        try:
            with self._db_connection() as conn, conn.cursor() as cur:
                cur.execute("""
                    SELECT reference_number, origin, destination, 
                           equipment_type, rate::float, commodity
                    FROM loads
                    WHERE UPPER(reference_number) = %s
                """, (reference_number,))

                columns = [desc[0] for desc in cur.description]
                result = cur.fetchone()

                if not result:
                    return self._send_error(404, "Load not found",
                                            {"reference_number": reference_number})

                load_data = dict(zip(columns, result))
                self._send_response(load_data)

        except psycopg2.Error as e:
            logger.error(f"Database error: {str(e)}")
            self._send_error(500, "Database operation failed")

    def _handle_search_request(self, params):
        try:
            with self._db_connection() as conn, conn.cursor() as cur:
                base_query = """
                    SELECT reference_number, origin, destination, 
                           equipment_type, rate::float, commodity
                    FROM loads
                    WHERE 1=1
                """
                conditions = []
                values = []

                if params.get('origin'):
                    conditions.append("origin ILIKE %s")
                    values.append(f"%{params['origin'][0]}%")

                if params.get('destination'):
                    conditions.append("destination ILIKE %s")
                    values.append(f"%{params['destination'][0]}%")

                if params.get('equipment_type'):
                    conditions.append("equipment_type ILIKE %s")
                    values.append(f"%{params['equipment_type'][0]}%")

                if conditions:
                    query = base_query + " AND " + " AND ".join(conditions)
                    cur.execute(query, values)
                else:
                    cur.execute(base_query)

                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]

                response = {
                    "count": len(results),
                    "results": results,
                    "message": "No matching loads found" if not results else None
                }
                self._send_response(response)

        except psycopg2.Error as e:
            logger.error(f"Database error: {str(e)}")
            self._send_error(500, "Database operation failed")

    def do_GET(self):
        if not self._authenticate():
            return

        parsed_url = urlparse(self.path)
        reference_number = self._get_reference_number_from_path(parsed_url.path)

        if reference_number:
            self._handle_reference_number_request(reference_number)
        else:
            if parsed_url.path.rstrip('/') != self.ROUTE:
                return self._send_error(404, "Invalid endpoint")

            params = parse_qs(parsed_url.query)
            self._handle_search_request(params)


def run(port=8001):
    server = HTTPServer(('', port), LoadService)
    logger.info(f"Load Service running on port {port}")
    server.serve_forever()


if __name__ == '__main__':
    run()