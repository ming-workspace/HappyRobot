# verify_carrier.py
import os
import json
import requests
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VerifyCarrierHandler(BaseHTTPRequestHandler):
    ROUTE = '/carriers/'

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

    def _verify_mc(self, mc_number):
        if not mc_number.isdigit() or len(mc_number) != 6:
            self._send_error(400, "Invalid MC number format",
                             {"expected": "6 digits", "received": mc_number})
            return None  # Terminate execution here

        try:
            response = requests.get(
                f"{os.getenv('FMCSA_BASE_URL')}/{mc_number}",
                params={'webKey': os.getenv('FMCSA_WEB_KEY')},
                timeout=10
            )

            if response.status_code == 404:
                return {"valid": False, "mc_number": mc_number}

            response.raise_for_status()
            content = response.json().get('content', [])
            return {
                "valid": bool(content),
                "mc_number": mc_number,
                **({} if not content else {
                    "carrier_name": content[0].get('legalName'),
                    "dot_number": content[0].get('dotNumber'),
                    "address": {
                        "city": content[0].get('phyCity'),
                        "state": content[0].get('phyState'),
                        "zipcode": content[0].get('phyZipcode')
                    }
                })
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"FMCSA API error: {str(e)}")
            self._send_error(503, "Carrier service unavailable")
            return None
        except Exception as e:
            logger.error(f"Processing error: {str(e)}")
            self._send_error(500, "Internal server error")
            return None

    def do_GET(self):
        if not self.path.startswith(self.ROUTE):
            return self._send_error(404, "Invalid endpoint")

        if not self._authenticate():
            return

        try:
            mc_number = self.path[len(self.ROUTE):].split('/')[0]
            if not mc_number:
                return self._send_error(400, "Missing MC number")

            result = self._verify_mc(mc_number)
            if result is not None:  # Only process if no errors were sent
                self._send_response(result)
        except Exception as e:
            logger.error(f"Processing error: {str(e)}")
            self._send_error(500, "Internal server error")


def run_server(port=8000):
    server = HTTPServer(('', port), VerifyCarrierHandler)
    logger.info(f"Carrier service running on port {port}")
    server.serve_forever()


if __name__ == '__main__':
    run_server()