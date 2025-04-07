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

        logger.info(f"Received API Key Header: {'Present' if api_key else 'Missing'}")
        logger.info(f"Configured Keys Count: {len(valid_keys)}")
        logger.info(f"Key Match Status: {api_key in valid_keys}")

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

    def _normalize_param(self, value):
        """Normalize parameter values for case-insensitive matching"""
        return ' '.join(value.replace(',', ' ').strip().split())

    def _decode_parameters(self, raw_params):
        decoded = {}
        for key, values in raw_params.items():
            if key == 'reference_number':
                decoded_values = []
                for v in values:
                    decoded_values.extend(unquote(v).strip().split(','))
                decoded[key] = [v.strip().upper() for v in decoded_values if v.strip()]
            else:
                processed = []
                for v in values:
                    cleaned = unquote(v).strip()
                    if key in ['origin', 'destination', 'equipment_type']:
                        cleaned = ' '.join(cleaned.replace(',', ' ').strip().split())
                    processed.append(cleaned)
                decoded[key] = processed
        return decoded

    def _build_query(self, params):
        base_query = """
            SELECT 
                reference_number, 
                origin, 
                destination,
                equipment_type, 
                rate::float,
                commodity
            FROM loads
            WHERE 1=1
        """
        conditions = []
        values = []

        # Reference number search (exact match)
        if params.get('reference_number'):
            ref_nums = params['reference_number']
            if ref_nums:
                conditions.append("UPPER(reference_number) = ANY(%s)")
                values.append(ref_nums)
                return base_query + " AND " + " AND ".join(conditions), values

        # Lane search (case-insensitive partial match)
        lane_params = ['origin', 'destination', 'equipment_type']
        if all(params.get(p) for p in lane_params):
            origin = params['origin'][0]
            conditions.append("origin ILIKE %s")
            values.append(f"%{origin}%")

            destination = params['destination'][0]
            conditions.append("destination ILIKE %s")
            values.append(f"%{destination}%")

            equipment = params['equipment_type'][0]
            conditions.append("equipment_type ILIKE %s")
            values.append(f"%{equipment}%")

            return base_query + " AND " + " AND ".join(conditions), values

        # No valid parameters case
        return base_query + " AND FALSE", []

    def _search_loads(self, params):
        try:
            query, values = self._build_query(params)
            with self._db_connection() as conn, conn.cursor() as cur:
                cur.execute(query, values)
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Database error: {str(e)}")
            return []

    def do_GET(self):
        parsed_path = urlparse(self.path)
        clean_path = parsed_path.path.rstrip('/')

        if clean_path != self.ROUTE:
            return self._send_error(404, f"Invalid endpoint: {parsed_path.path}")

        if not self._authenticate():
            return

        try:
            raw_params = parse_qs(parsed_path.query)
            params = self._decode_parameters(raw_params)
            results = self._search_loads(params)

            response = {
                "count": len(results),
                "results": results,
                "message": "No matching loads found" if not results else None
            }

            self._send_response(response)

        except Exception as e:
            logger.error(f"Processing error: {str(e)}", exc_info=True)
            self._send_response({
                "count": 0,
                "results": [],
                "message": "No matching loads found"
            })


def run(port=8001):
    server = HTTPServer(('', port), LoadService)
    logger.info(f"Load Service running on port {port}")
    server.serve_forever()


if __name__ == '__main__':
    run()