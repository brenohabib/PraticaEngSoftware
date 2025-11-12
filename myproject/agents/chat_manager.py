"""
Gerenciador de sessões de chat para manter contexto entre conversas.
"""

import uuid
import time
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ChatSessionManager:
    """
    Gerencia sessões de chat com TTL (Time To Live) para evitar acúmulo de memória.
    Cada sessão mantém o objeto de chat do Gemini para preservar o histórico.
    """

    def __init__(self, session_ttl_minutes=30):
        """
        Inicializa o gerenciador de sessões.

        Args:
            session_ttl_minutes (int): Tempo de vida da sessão em minutos
        """
        self.sessions: Dict[str, dict] = {}
        self.session_ttl = timedelta(minutes=session_ttl_minutes)
        logger.info(f"ChatSessionManager inicializado com TTL de {session_ttl_minutes} minutos")

    def create_session(self, chat_object, agent_type="simple") -> str:
        """
        Cria uma nova sessão de chat.

        Args:
            chat_object: Objeto de chat do Gemini (retornado por client.chats.create())
            agent_type (str): Tipo do agente ('simple' ou 'embedding')

        Returns:
            str: ID único da sessão
        """
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "chat": chat_object,
            "agent_type": agent_type,
            "created_at": datetime.now(),
            "last_accessed": datetime.now(),
            "message_count": 0
        }
        logger.info(f"Nova sessão criada: {session_id} (tipo: {agent_type})")
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        """
        Recupera uma sessão existente.

        Args:
            session_id (str): ID da sessão

        Returns:
            dict: Dados da sessão ou None se não existir/expirada
        """
        # Limpa sessões expiradas antes de buscar
        self._cleanup_expired_sessions()

        session = self.sessions.get(session_id)
        if session:
            # Verifica se a sessão ainda está válida
            if self._is_session_valid(session):
                session["last_accessed"] = datetime.now()
                logger.info(f"Sessão recuperada: {session_id}")
                return session
            else:
                # Remove sessão expirada
                logger.info(f"Sessão expirada removida: {session_id}")
                del self.sessions[session_id]
                return None

        logger.warning(f"Sessão não encontrada: {session_id}")
        return None

    def increment_message_count(self, session_id: str):
        """
        Incrementa o contador de mensagens de uma sessão.

        Args:
            session_id (str): ID da sessão
        """
        session = self.sessions.get(session_id)
        if session:
            session["message_count"] += 1
            session["last_accessed"] = datetime.now()

    def delete_session(self, session_id: str) -> bool:
        """
        Remove uma sessão específica.

        Args:
            session_id (str): ID da sessão

        Returns:
            bool: True se removida com sucesso, False se não existia
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Sessão deletada: {session_id}")
            return True
        return False

    def _is_session_valid(self, session: dict) -> bool:
        """
        Verifica se uma sessão ainda é válida (não expirou).

        Args:
            session (dict): Dados da sessão

        Returns:
            bool: True se válida, False se expirada
        """
        elapsed = datetime.now() - session["last_accessed"]
        return elapsed < self.session_ttl

    def _cleanup_expired_sessions(self):
        """
        Remove todas as sessões expiradas.
        """
        expired_sessions = [
            session_id
            for session_id, session in self.sessions.items()
            if not self._is_session_valid(session)
        ]

        for session_id in expired_sessions:
            del self.sessions[session_id]
            logger.info(f"Sessão expirada removida: {session_id}")

        if expired_sessions:
            logger.info(f"{len(expired_sessions)} sessões expiradas removidas")

    def get_session_count(self) -> int:
        """
        Retorna o número de sessões ativas.

        Returns:
            int: Número de sessões
        """
        self._cleanup_expired_sessions()
        return len(self.sessions)

    def get_session_info(self, session_id: str) -> Optional[dict]:
        """
        Retorna informações sobre uma sessão (sem o objeto chat).

        Args:
            session_id (str): ID da sessão

        Returns:
            dict: Informações da sessão ou None
        """
        session = self.get_session(session_id)
        if session:
            return {
                "session_id": session_id,
                "agent_type": session["agent_type"],
                "created_at": session["created_at"].isoformat(),
                "last_accessed": session["last_accessed"].isoformat(),
                "message_count": session["message_count"]
            }
        return None


# Instância global do gerenciador
# Para produção, considere usar cache distribuído (Redis) em vez de memória
chat_manager = ChatSessionManager(session_ttl_minutes=30)
