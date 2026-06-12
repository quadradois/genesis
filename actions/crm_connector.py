import json
import sys
from pathlib import Path
from typing import Optional
import requests


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
CRM_CONFIG_PATH = BASE_DIR / "config" / "crm_config.json"


def _load_config() -> dict:
    try:
        return json.loads(CRM_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _get_api_key(config: dict) -> str:
    key = config.get("api_key", "")
    auth = config.get("headers", {}).get("Authorization", "")
    if not key and auth.startswith("Bearer "):
        key = auth[7:]
    return key


class CRMClient:
    def __init__(self):
        self._config = _load_config()
        self._base_url = self._config.get("api_url", "").rstrip("/")
        self._headers = self._config.get("headers", {"Content-Type": "application/json"})
        self._endpoints = self._config.get("endpoints", {})
        self._timeout = self._config.get("timeout", 30)

    def _check_ready(self) -> Optional[str]:
        if not self._base_url:
            return "CRM nao configurado. Edite config/crm_config.json com a URL e chave da API."
        key = _get_api_key(self._config)
        if not key:
            return "CRM: chave de API nao configurada em config/crm_config.json"
        return None

    def _url(self, endpoint_key: str, path: str = "") -> str:
        ep = self._endpoints.get(endpoint_key, f"/{endpoint_key}")
        return f"{self._base_url}{ep}{path}"

    def _request(self, method: str, url: str, **kwargs) -> str:
        error = self._check_ready()
        if error:
            return error

        try:
            resp = requests.request(
                method,
                url,
                headers=self._headers,
                timeout=self._timeout,
                **kwargs,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return json.dumps(data, ensure_ascii=False, indent=2)
            elif resp.status_code == 401:
                return "CRM: erro de autenticacao (401). Verifique o token em config/crm_config.json"
            elif resp.status_code == 403:
                return "CRM: acesso negado (403). Verifique as permissoes do token."
            elif resp.status_code == 404:
                return "CRM: recurso nao encontrado (404). Verifique a URL base."
            elif resp.status_code == 422:
                try:
                    detail = resp.json()
                    return f"CRM: dados invalidos (422): {json.dumps(detail, ensure_ascii=False)}"
                except Exception:
                    return f"CRM: dados invalidos (422): {resp.text[:200]}"
            else:
                return f"CRM: erro HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.exceptions.ConnectionError:
            return f"CRM: nao foi possivel conectar em {self._base_url}. Verifique a URL."
        except requests.exceptions.Timeout:
            return "CRM: requisicao excedeu o tempo limite."
        except Exception as e:
            return f"CRM: erro inesperado: {e}"

    # --- Properties (Imoveis) ---

    def list_properties(self, filters: Optional[dict] = None) -> str:
        params = filters or {}
        return self._request("GET", self._url("properties"), params=params)

    def get_property(self, property_id: str) -> str:
        return self._request("GET", self._url("properties", f"/{property_id}"))

    def create_property(self, data: dict) -> str:
        return self._request("POST", self._url("properties"), json=data)

    def update_property(self, property_id: str, data: dict) -> str:
        return self._request("PUT", self._url("properties", f"/{property_id}"), json=data)

    def delete_property(self, property_id: str) -> str:
        return self._request("DELETE", self._url("properties", f"/{property_id}"))

    # --- Leads ---

    def list_leads(self, filters: Optional[dict] = None) -> str:
        params = filters or {}
        return self._request("GET", self._url("leads"), params=params)

    def get_lead(self, lead_id: str) -> str:
        return self._request("GET", self._url("leads", f"/{lead_id}"))

    def create_lead(self, data: dict) -> str:
        return self._request("POST", self._url("leads"), json=data)

    def update_lead_status(self, lead_id: str, status: str) -> str:
        return self._request("PATCH", self._url("leads", f"/{lead_id}/status"), json={"status": status})

    # --- Appointments (Agendamentos) ---

    def list_appointments(self, filters: Optional[dict] = None) -> str:
        params = filters or {}
        return self._request("GET", self._url("appointments"), params=params)

    def create_appointment(self, data: dict) -> str:
        return self._request("POST", self._url("appointments"), json=data)

    def cancel_appointment(self, appointment_id: str) -> str:
        return self._request("PATCH", self._url("appointments", f"/{appointment_id}/cancel"))

    # --- Clients ---

    def list_clients(self, filters: Optional[dict] = None) -> str:
        params = filters or {}
        return self._request("GET", self._url("clients"), params=params)

    def get_client(self, client_id: str) -> str:
        return self._request("GET", self._url("clients", f"/{client_id}"))

    def create_client(self, data: dict) -> str:
        return self._request("POST", self._url("clients"), json=data)

    def update_client(self, client_id: str, data: dict) -> str:
        return self._request("PUT", self._url("clients", f"/{client_id}"), json=data)

    # --- Generic / Direct ---

    def custom_query(self, endpoint: str, method: str = "GET", data: Optional[dict] = None) -> str:
        url = f"{self._base_url}{endpoint}" if endpoint.startswith("/") else endpoint
        if method.upper() == "GET":
            return self._request("GET", url, params=data)
        return self._request(method.upper(), url, json=data)

    def status(self) -> str:
        error = self._check_ready()
        if error:
            return error
        try:
            resp = requests.get(self._base_url, headers=self._headers, timeout=10)
            if resp.status_code < 500:
                return f"CRM: conectado ({resp.status_code})"
            return f"CRM: servidor retornou {resp.status_code}"
        except Exception as e:
            return f"CRM: offline — {e}"


crm = CRMClient()
