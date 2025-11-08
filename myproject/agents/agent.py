import os
import json
import time
import logging
from abc import ABC, abstractmethod
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv()


class BaseAgent(ABC):
    """
    Classe base abstrata para agentes que utilizam a API do Gemini.

    Fornece funcionalidades comuns como:
    - Configuração do cliente Gemini
    - Lógica de retry com backoff exponencial
    - Logging padronizado
    """

    def __init__(self, model_name='gemini-2.5-flash-lite'):
        """
        Inicializa o agente base.

        Args:
            model_name (str): Nome do modelo Gemini a ser utilizado
        """
        self.model_name = model_name
        self.logger = logging.getLogger(self.__class__.__name__)

        # Configura a API do Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.logger.error("GEMINI_API_KEY não encontrada nas variáveis de ambiente")
            raise ValueError("GEMINI_API_KEY não configurada")

        self.client = genai.Client(api_key=api_key)
        self.logger.info(f"Agente {self.__class__.__name__} inicializado com modelo {model_name}")

    def _retry_with_backoff(self, operation, max_retries=3, retry_delay=2, operation_name="operação"):
        """
        Executa uma operação com retry e backoff exponencial.

        Args:
            operation (callable): Função a ser executada
            max_retries (int): Número máximo de tentativas
            retry_delay (int): Tempo base de espera entre tentativas em segundos
            operation_name (str): Nome da operação para logging

        Returns:
            dict: Resultado da operação ou mensagem de erro
        """
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(f"Tentativa {attempt}/{max_retries} - Executando {operation_name}...")
                result = operation()
                self.logger.info(f"{operation_name.capitalize()} concluída com sucesso!")
                return result

            except json.JSONDecodeError as e:
                self.logger.error(f"Tentativa {attempt}/{max_retries} - Erro ao decodificar JSON: {str(e)}")

                if attempt < max_retries:
                    wait_time = retry_delay * attempt
                    self.logger.info(f"Aguardando {wait_time}s antes da próxima tentativa...")
                    time.sleep(wait_time)
                else:
                    return {
                        "error": f"Falha ao decodificar JSON após todas as tentativas: {str(e)}",
                        "response": None,
                        "attempts": max_retries
                    }

            except ValueError as e:
                self.logger.error(f"Tentativa {attempt}/{max_retries} - Erro de validação: {str(e)}")

                if attempt < max_retries:
                    wait_time = retry_delay * attempt  # Backoff linear
                    self.logger.info(f"Aguardando {wait_time}s antes da próxima tentativa...")
                    time.sleep(wait_time)
                else:
                    return {
                        "error": f"Erro de validação após todas as tentativas: {str(e)}",
                        "response": None,
                        "attempts": max_retries
                    }

            except Exception as e:
                self.logger.error(f"Tentativa {attempt}/{max_retries} - Erro inesperado: {str(e)}")

                if attempt < max_retries:
                    wait_time = retry_delay * attempt
                    self.logger.info(f"Aguardando {wait_time}s antes da próxima tentativa...")
                    time.sleep(wait_time)
                else:
                    return {
                        "error": f"Erro inesperado após todas as tentativas: {str(e)}",
                        "response": None,
                        "attempts": max_retries
                    }

        # Se chegou aqui, todas as tentativas falharam
        return {
            "error": f"Todas as tentativas de {operation_name} falharam",
            "response": None,
            "attempts": max_retries
        }

    def _clean_json_response(self, response_text):
        """
        Limpa a resposta da API para extrair apenas o JSON válido.
        Remove marcadores de código markdown (```json e ```).

        Args:
            response_text (str): Texto da resposta da API

        Returns:
            str: JSON limpo
        """
        json_str = response_text.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        elif json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]

        return json_str.strip()

    @abstractmethod
    def process(self, *args, **kwargs):
        """
        Método abstrato que deve ser implementado pelas subclasses.
        Define o comportamento principal do agente.
        """
        pass
