import json
import sys
import uuid
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


def _resolve_key(config: dict) -> str:
    key = config.get("api_key", "")
    auth = config.get("headers", {}).get("Authorization", "")
    if not key and auth.startswith("Bearer "):
        key = auth[7:]
    if "${COPILOT_API_KEY}" in key:
        key = key.replace("${COPILOT_API_KEY}", "")
    return key


class CopilotCRM:
    def __init__(self):
        self._config = _load_config()
        self._base_url = self._config.get("api_url", "").rstrip("/")
        self._api_key = _resolve_key(self._config)
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        self._tenant_header = self._config.get("tenant_header", "X-Tenant-Id")
        self._default_tenant = self._config.get("default_tenant_id", 1)
        self._endpoints = self._config.get("endpoints", {})
        self._timeout = self._config.get("timeout", 30)

    def _check_ready(self) -> Optional[str]:
        if not self._base_url:
            return "CRM nao configurado. Edite config/crm_config.json com a URL."
        if not self._api_key:
            return "CRM: chave de API nao configurada em config/crm_config.json"
        return None

    def _build_headers(self, tenant_id: Optional[int] = None, extra: Optional[dict] = None) -> dict:
        h = dict(self._headers)
        if tenant_id is not None:
            h[self._tenant_header] = str(tenant_id)
        if extra:
            h.update(extra)
        return h

    def _url(self, endpoint_key: str, **path_params) -> str:
        template = self._endpoints.get(endpoint_key)
        if not template:
            return f"{self._base_url}/{endpoint_key}"
        for k, v in path_params.items():
            template = template.replace(f"{{{k}}}", str(v))
        return f"{self._base_url}{template}"

    def _request(self, method: str, url: str, tenant_id: Optional[int] = None,
                 extra_headers: Optional[dict] = None, **kwargs) -> str:
        error = self._check_ready()
        if error:
            return error
        try:
            resp = requests.request(
                method, url,
                headers=self._build_headers(tenant_id, extra_headers),
                timeout=self._timeout, **kwargs,
            )

            if resp.status_code in (200, 201):
                return json.dumps(resp.json(), ensure_ascii=False, indent=2)

            errors = {
                401: "CRM: autenticacao falhou (401). Verifique a chave em config/crm_config.json",
                403: "CRM: acesso negado (403). Chave sem permissao.",
                404: "CRM: recurso nao encontrado (404).",
                409: "CRM: conflito (409) — estado nao permite acao.",
                422: "CRM: dados invalidos (422).",
                429: "CRM: rate limit (429). Aguarde e tente novamente.",
            }
            if resp.status_code in errors:
                msg = errors[resp.status_code]
                try:
                    body = resp.json()
                    if "error" in body:
                        msg += f" Detalhe: {body['error']}"
                except Exception:
                    pass
                return msg

            if resp.status_code >= 500:
                return f"CRM: erro no servidor ({resp.status_code}). Tente novamente."

            return f"CRM: erro HTTP {resp.status_code}: {resp.text[:200]}"

        except requests.exceptions.ConnectionError:
            return f"CRM: nao foi possivel conectar em {self._base_url}. Verifique a URL."
        except requests.exceptions.Timeout:
            return "CRM: requisicao excedeu o tempo limite."
        except Exception as e:
            return f"CRM: erro inesperado: {e}"

    def list_events(self, after_id: int = 0, limit: int = 100,
                    types: str = "lead.created", tenant_id: Optional[int] = None) -> str:
        params = {"after_id": after_id, "limit": min(limit, 500)}
        if types:
            params["types"] = types
        if tenant_id is not None:
            params["tenant_id"] = tenant_id
        return self._request("GET", self._url("events"), params=params)

    def list_leads(self, tenant_id: int = 0, page: int = 1, per_page: int = 50,
                   status: str = "", assigned_to: Optional[int] = None,
                   unassigned: bool = False) -> str:
        params = {"page": page, "per_page": min(per_page, 100)}
        if status:
            params["status"] = status
        if assigned_to is not None:
            params["assigned_to"] = assigned_to
        if unassigned:
            params["unassigned"] = "true"
        tid = tenant_id or self._default_tenant
        return self._request("GET", self._url("leads"), tenant_id=tid, params=params)

    def get_lead(self, lead_id: int, tenant_id: int = 0) -> str:
        tid = tenant_id or self._default_tenant
        return self._request("GET", self._url("lead_detail", lead_id=lead_id), tenant_id=tid)

    def assign_lead(self, lead_id: int, user_id: int, tenant_id: int = 0) -> str:
        tid = tenant_id or self._default_tenant
        return self._request("POST", self._url("lead_assign", lead_id=lead_id),
                             tenant_id=tid, json={"user_id": user_id})

    def send_message(self, lead_id: int, text: str,
                     tenant_id: int = 0, idempotency_key: Optional[str] = None) -> str:
        tid = tenant_id or self._default_tenant
        key = idempotency_key or f"agent-os-lead-{lead_id}-{uuid.uuid4().hex[:8]}"
        return self._request("POST", self._url("lead_message", lead_id=lead_id),
                             tenant_id=tid, extra_headers={"Idempotency-Key": key},
                             json={"text": text})

    def list_users(self, tenant_id: int = 0) -> str:
        tid = tenant_id or self._default_tenant
        return self._request("GET", self._url("users"), tenant_id=tid)

    def custom_query(self, endpoint: str, method: str = "GET",
                     tenant_id: Optional[int] = None,
                     data: Optional[dict] = None, extra_headers: Optional[dict] = None) -> str:
        url = f"{self._base_url}{endpoint}" if endpoint.startswith("/") else endpoint
        if method.upper() == "GET":
            return self._request("GET", url, tenant_id=tenant_id,
                                 extra_headers=extra_headers, params=data)
        return self._request(method.upper(), url, tenant_id=tenant_id,
                             extra_headers=extra_headers, json=data)

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


crm = CopilotCRM()
