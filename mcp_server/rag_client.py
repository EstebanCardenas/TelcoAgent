from cli.config import Settings
import requests as req
import json


class RagClient:
    """
    Cliente que permite hacer consultas sobre la base de conocimiento
    pública de telecom.
    """

    def __init__(self, settings: Settings):
        self.base_url = settings.rag_base_url
        self.email = settings.rag_email
        self.password = settings.rag_password
        self.collection = settings.rag_collection
        self.access_token = None

    def _get_headers(self) -> str:
        base = {
            "Content-Type": "application/json"
        }
        if self.access_token != None:
            base['Authorization'] = f'Bearer {self.access_token}'
        return base

    def login(self):
        data = {
            "email": self.email,
            "password": self.password,
        }
        url = self.base_url + "/login"
        res = req.post(url, json=data, headers=self._get_headers())
        res.raise_for_status()

        self.access_token = res.json()["access_token"]

    def query_knowledge_base(self, query: str) -> str:
        if self.access_token == None:
            raise Exception('El cliente RAG aún no se encuentra autenticado.')

        data = {
            "pregunta": query,
            "collection": self.collection,
        }
        url = self.base_url + "/ask"
        res = req.post(url, json=data, headers=self._get_headers())
        res.raise_for_status()

        return res.json()["respuesta"]
