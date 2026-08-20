from cli.config import Settings
import requests as req
from observability.tracing import trazable


class RagError(Exception):
    """Fallo al consultar el RAG, con un código estable.

    El código permite decidir qué hacer (reintentar, degradar o avisar) sin
    interpretar el texto del mensaje.

    Códigos: sin_configurar | credenciales_invalidas | pregunta_rechazada |
             coleccion_no_existe | rate_limit | sin_conexion | error_servicio |
             respuesta_invalida
    """

    def __init__(self, codigo: str, mensaje: str, reintentar_en: int | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.reintentar_en = reintentar_en


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

    @staticmethod
    def _segundos_de_espera(res) -> int | None:
        """El header `Retry-After` que acompaña a un 429."""
        valor = res.headers.get("Retry-After")
        try:
            return int(float(valor)) if valor is not None else None
        except (TypeError, ValueError):
            return None

    @trazable(name="rag_login")
    def login(self) -> None:
        """Autentica contra la API del RAG (POST /api/v1/login) y almacena el token Bearer."""
        if not self.base_url or not self.email or not self.password:
            raise RagError(
                "sin_configurar",
                "Credenciales o URL del RAG (RAG_BASE_URL, RAG_EMAIL, RAG_PASSWORD) no configuradas.",
            )

        data = {
            "email": self.email,
            "password": self.password,
        }
        url = f"{self.base_url}/login"
        try:
            res = req.post(url, json=data, headers={"Content-Type": "application/json"}, timeout=30)
        except req.RequestException as exc:
            raise RagError("sin_conexion", f"No hay conexión con el servicio RAG ({self.base_url}): {exc}")

        if res.status_code == 401:
            raise RagError("credenciales_invalidas", "El servicio RAG rechazó las credenciales del grupo (401).")
        if res.status_code != 200:
            raise RagError("error_servicio", f"Login al RAG falló con status {res.status_code}: {res.text[:200]}")

        try:
            self.access_token = res.json()["access_token"]
        except (ValueError, KeyError):
            raise RagError("respuesta_invalida", "El login del RAG no devolvió un access_token utilizable.")

    @trazable(name="rag_query_knowledge_base")
    def query_knowledge_base(self, query: str) -> dict:

        """Consulta la base de conocimiento del RAG (POST /api/v1/ask).

        Devuelve `{"respuesta": str, "fuentes": list[str]}` o levanta `RagError`.
        Un 401 se reintenta una sola vez tras renovar el token.
        """
        if self.access_token is None:
            self.login()

        res = self._ask(query)

        if res.status_code == 401:
            # El token expiró a mitad de la conversación: renovar y reintentar una vez.
            self.access_token = None
            self.login()
            res = self._ask(query)

        if res.status_code == 429:
            espera = self._segundos_de_espera(res)
            raise RagError(
                "rate_limit",
                "Se alcanzó la cuota de consultas del RAG (10 por minuto / 100 por día).",
                reintentar_en=espera,
            )
        if res.status_code == 400:
            raise RagError("pregunta_rechazada", "El servicio RAG rechazó la pregunta (vacía o contenido no permitido).")
        if res.status_code == 404:
            raise RagError("coleccion_no_existe", f"La colección '{self.collection}' no existe en el servicio RAG.")
        if res.status_code != 200:
            raise RagError("error_servicio", f"El servicio RAG respondió status {res.status_code}: {res.text[:200]}")

        try:
            cuerpo = res.json()
        except ValueError:
            raise RagError("respuesta_invalida", "El servicio RAG devolvió un cuerpo que no es JSON.")

        respuesta = (cuerpo.get("respuesta") or "").strip()
        if not respuesta:
            raise RagError("respuesta_invalida", "El servicio RAG devolvió una respuesta vacía.")

        return {"respuesta": respuesta, "fuentes": cuerpo.get("files_consulted") or []}

    def _ask(self, query: str):
        data = {
            "pregunta": query,
            "collection": self.collection,
            "evaluate": False,
        }
        url = f"{self.base_url}/ask"
        try:
            return req.post(url, json=data, headers=self._get_headers(), timeout=60)
        except req.RequestException as exc:
            raise RagError("sin_conexion", f"No hay conexión con el servicio RAG ({self.base_url}): {exc}")
