# find_available_loads.py
import os
import csv
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LoadService(BaseHTTPRequestHandler):
    loads = []
    ROUTE = '/loads'

    @classmethod
    def load_data(cls):
        csv_path = os.getenv("LOAD_CSV_PATH", "allowed_references.csv")
        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                cls.loads = [{
                    'reference_number': row['reference_number'].strip().upper(),
                    'origin': row['origin'].strip().upper(),
                    'destination': row['destination'].strip().upper(),
                    'equipment_type': row['equipment_type'].strip().upper(),
                    'rate': float(row['rate']),
                    'commodity': row['commodity'].strip().upper()
                } for row in reader]
            logger.info(f"Loaded {len(cls.loads)} loads")
        except Exception as e:
            logger.error(f"CSV load failed: {str(e)}")
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

    def _handle_search(self):
        query = urlparse(self.path).query
        params = parse_qs(query)
        ref_nums = [r.strip().upper() for r in params.get('reference_number', [''])[0].split(',') if r.strip()]
        origin = params.get('origin', [''])[0].strip().upper()
        dest = params.get('destination', [''])[0].strip().upper()
        equipment = params.get('equipment_type', [''])[0].strip().upper()

        # Validation logic
        if not ref_nums and (origin or dest):
            missing = []
            if not origin: missing.append('origin')
            if not dest: missing.append('destination')
            if missing:
                return self._send_error(400, "Missing required parameters", {"missing": missing})

        # Search logic
        results = []
        if ref_nums:
            results = [load for load in self.loads if load['reference_number'] in ref_nums]

        if not results and origin and dest:
            results = [
                load for load in self.loads
                if load['origin'] == origin
                   and load['destination'] == dest
                   and (not equipment or equipment in load['equipment_type'].split(' OR '))
            ]

        return {
            "count": len(results),
            "results": results,
            "message": "No matches found" if not results else None
        }

    def do_GET(self):
        if not self.path.startswith(self.ROUTE):
            return self._send_error(404, "Invalid endpoint")

        if not self._authenticate():
            return

        try:
            if self.path == self.ROUTE:
                result = self._handle_search()
                if result['count'] == 0:
                    self._send_response(result, 404)
                else:
                    self._send_response(result)
            else:
                self._send_error(404, "Invalid endpoint")
        except Exception as e:
            logger.error(f"Processing error: {str(e)}")
            self._send_error(500, "Internal server error")


def run(port=8001):
    LoadService.load_data()
    server = HTTPServer(('', port), LoadService)
    logger.info(f"Load service running on port {port}")
    server.serve_forever()


if __name__ == '__main__':
    run()