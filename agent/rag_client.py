from cli.config import Settings
import requests as req


class RagClient:
    """
    Cliente que permite hacer consultas sobre la base de conocimiento
    pública de telecom mediante el servicio central de RAG.
    """

    def __init__(self, settings: Settings):
        base = (settings.rag_base_url or "").rstrip("/")
        if base and not base.endswith("/api/v1"):
            base = f"{base}/api/v1"
        self.base_url = base
        self.email = settings.rag_email
        self.password = settings.rag_password
        self.collection = settings.rag_collection or "telecom"
        self.access_token = None

    def _get_headers(self) -> dict:
        headers = {
            "Content-Type": "application/json"
        }
        if self.access_token is not None:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def login(self) -> None:
        """Autentica contra la API del RAG (POST /api/v1/login) y almacena el token Bearer."""
        if not self.base_url or not self.email or not self.password:
            raise ValueError("Credenciales o URL del RAG (RAG_BASE_URL, RAG_EMAIL, RAG_PASSWORD) no configuradas.")
        
        data = {
            "email": self.email,
            "password": self.password,
        }
        url = f"{self.base_url}/login"
        res = req.post(url, json=data, headers={"Content-Type": "application/json"}, timeout=30)
        res.raise_for_status()
        self.access_token = res.json()["access_token"]

    def query_knowledge_base(self, query: str) -> str:
        """Consulta la base de conocimiento del RAG (POST /api/v1/ask) utilizando el token de autenticación."""
        if self.access_token is None:
            self.login()

        data = {
            "pregunta": query,
            "collection": self.collection,
            "evaluate": False,
        }
        url = f"{self.base_url}/ask"
        res = req.post(url, json=data, headers=self._get_headers(), timeout=60)
        res.raise_for_status()
        return res.json()["respuesta"]
