# find_available_loads_db.py

import os
import json
import logging
import psycopg2
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
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


class LoadServiceDB(BaseHTTPRequestHandler):
    ROUTE = '/loads_db'

    def _db_connection(self):
        try:
            conn = psycopg2.connect(
                dbname=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                host=os.getenv('DB_HOST', 'postgres'),
                port=os.getenv('DB_PORT', '5432'),
                connect_timeout=5
            )
            conn.autocommit = True
            return conn
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
            SELECT 
                reference_number, 
                origin, 
                destination,
                equipment_type, 
                rate::float,  -- Explicit cast to float
                commodity
            FROM loads
            WHERE 1=1
        """
        conditions = []
        values = []

        if 'reference_number' in params:
            ref_nums = [r.strip().upper() for r in params['reference_number'][0].split(',') if r.strip()]
            if ref_nums:
                conditions.append("reference_number = ANY(%s)")
                values.append(ref_nums)

        if 'origin' in params:
            origin = params['origin'][0].strip().upper()
            if origin:
                conditions.append("origin = %s")
                values.append(origin)

        if 'destination' in params:
            dest = params['destination'][0].strip().upper()
            if dest:
                conditions.append("destination = %s")
                values.append(dest)

        if 'equipment_type' in params:
            equipment = params['equipment_type'][0].strip().upper()
            if equipment:
                conditions.append("equipment_type ILIKE %s")
                values.append(f"%{equipment}%")

        query = base_query
        if conditions:
            query += " AND " + " AND ".join(conditions)

        return query, values

    def _search_loads(self, params):
        try:
            query, values = self._build_query(params)
            with self._db_connection() as conn, conn.cursor() as cur:
                cur.execute(query, values)
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Database query failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
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