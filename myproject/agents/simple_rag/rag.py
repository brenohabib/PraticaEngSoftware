from ..agent import BaseAgent

class SimpleRAGAgent(BaseAgent):
    def __init__(self, model_name='gemini-2.5-flash-lite'):
        """
        Inicializa o agente RAG simples.

        Args:
            model_name (str): Nome do modelo Gemini a ser utilizado
        """
        super().__init__(model_name)
        self.prompt_template = """
            Você é um assistente especializado em responder perguntas com base em documentos fornecidos.

            ### Instruções:
            - Responda à pergunta APENAS com base no contexto fornecido abaixo
            - Se a informação não estiver disponível no contexto, diga claramente "Nenhuma informação encontrada nos documentos fornecidos"
            - Seja direto e objetivo na resposta
            - Cite informações específicas dos documentos quando relevante
            - NÃO invente ou assuma informações que não estejam explicitamente nos documentos

            ### Contexto:
            {context}

            ### Pergunta:
            {question}

            ### Resposta:
        """

    def query(self, question, context="", max_retries=3, retry_delay=2):
        """
        Consulta o modelo RAG com uma pergunta e contexto.

        Args:
            question (str): Pergunta a ser respondida
            context (str): Contexto ou documentos para embasar a resposta (opcional)
            max_retries (int): Número máximo de tentativas em caso de falha
            retry_delay (int): Tempo de espera entre tentativas em segundos

        Returns:
            dict: Resposta do modelo ou mensagem de erro
        """
        # Validação inicial
        if not question or not question.strip():
            self.logger.error("Pergunta vazia fornecida")
            return {
                "error": "Pergunta não pode estar vazia",
                "response": None
            }

        # Monta o prompt completo
        full_prompt = self.prompt_template.format(
            context=context if context else "Nenhum documento de contexto fornecido.",
            question=question.strip()
        )

        # Define a operação de consulta que será executada com retry
        def query_operation():
            # Gera o conteúdo usando o modelo
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[full_prompt]
            )

            # Extrai o texto da resposta
            if not response or not response.text:
                raise ValueError("Resposta vazia da API")

            response_text = response.text.strip()

            return {
                "response": response_text,
                "context_used": bool(context.strip()),
                "error": None
            }

        # Executa a operação com retry
        return self._retry_with_backoff(
            operation=query_operation,
            max_retries=max_retries,
            retry_delay=retry_delay,
            operation_name="consulta RAG"
        )

    def process(self, question, context="", max_retries=3, retry_delay=2):
        """
        Implementação do método abstrato process().
        Alias para query() mantendo compatibilidade.

        Args:
            question (str): Pergunta a ser respondida
            context (str): Contexto ou documentos para embasar a resposta (opcional)
            max_retries (int): Número máximo de tentativas em caso de falha
            retry_delay (int): Tempo de espera entre tentativas em segundos

        Returns:
            dict: Resposta do modelo ou mensagem de erro
        """
        return self.query(question, context, max_retries, retry_delay)
