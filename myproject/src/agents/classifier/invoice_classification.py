import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))  # C:\myproject\src\agents\classifier
agents_dir = os.path.dirname(current_dir)  # C:\myproject\src\agents
sys.path.insert(0, agents_dir)

import extraction.invoice_extractor

import json
import logging
import google.generativeai as genai
from dotenv import load_dotenv

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv()

# Configura a API do Gemini
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    logger.error("GEMINI_API_KEY não encontrada nas variáveis de ambiente")
    raise ValueError("GEMINI_API_KEY não configurada")

genai.configure(api_key=api_key)

class ExpenseClassifierAgent:
    """
    Agente para classificar despesas de notas fiscais com base na descrição dos produtos,
    permitindo múltiplas classificações.
    """
    def __init__(self, model_name='gemini-1.5-flash'):
        """
        Inicializa o agente de classificação.

        Args:
            model_name (str): Nome do modelo Gemini a ser utilizado.
        """
        self.model = genai.GenerativeModel(model_name)
        self.prompt_template = """
        Você é um especialista em classificação de despesas agrícolas.
        Analise CADA ITEM na "descricao_produtos" do JSON abaixo e associe cada um à sua categoria de despesa correspondente.
        Retorne um JSON contendo uma única chave "classificacoes", que será uma lista de strings com TODAS as categorias de despesa encontradas, SEM REPETIÇÃO.

        CATEGORIAS VÁLIDAS:
        - INSUMOS AGRÍCOLAS (Ex: Sementes, Fertilizantes, Defensivos Agrícolas, Corretivos)
        - MANUTENÇÃO E OPERAÇÃO (Ex: Combustíveis, Lubrificantes, Peças, Parafusos, Pneus, Filtros, Ferramentas, Manutenção de Máquinas)
        - RECURSOS HUMANOS (Ex: Mão de Obra Temporária, Salários)
        - SERVIÇOS OPERACIONAIS (Ex: Frete, Transporte, Colheita Terceirizada, Secagem, Armazenagem, Pulverização)
        - INFRAESTRUTURA E UTILIDADES (Ex: Energia Elétrica, Arrendamento de Terras, Materiais de Construção, Reformas)
        - ADMINISTRATIVAS (Ex: Honorários Contábeis, Advocatícios, Agronômicos, Despesas Bancárias)
        - SEGUROS E PROTEÇÃO (Ex: Seguro Agrícola, Seguro de Máquinas/Veículos)
        - IMPOSTOS E TAXAS (Ex: ITR, IPTU, IPVA, INCRA-CCIR)
        - INVESTIMENTOS (Ex: Aquisição de Máquinas, Veículos, Imóveis, Infraestrutura Rural)
        - OUTRAS DESPESAS (Use esta categoria se nenhum item se encaixar claramente nas outras)

        JSON da Nota Fiscal:
        {json_data}

        IMPORTANTE:
        - A sua resposta deve ser APENAS um objeto JSON válido.
        - O JSON de resposta deve ter a seguinte estrutura: {{"classificacoes": ["CATEGORIA_1", "CATEGORIA_2", ...]}}
        - Não inclua explicações ou texto fora do JSON.
        - A lista de classificações não deve conter valores duplicados.
        """

    def _clean_json_response(self, response_text):
        """
        Limpa a resposta da API para extrair apenas o JSON válido.
        
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

    def classify_expense(self, invoice_json: dict) -> dict:
        """
        Adiciona a(s) classificação(ões) da despesa ao JSON da nota fiscal.

        Args:
            invoice_json (dict): Dicionário contendo os dados extraídos da nota fiscal.

        Returns:
            dict: O dicionário original com a adição do campo "classificacoes_despesa" (uma lista).
        """
        if "error" in invoice_json or not invoice_json.get("descricao_produtos"):
            invoice_json["classificacoes_despesa"] = ["CLASSIFICAÇÃO FALHOU"]
            logger.warning("JSON de entrada contém erro ou está sem descrição de produtos. Classificação abortada.")
            return invoice_json

        try:
            json_data_str = json.dumps(invoice_json, indent=2, ensure_ascii=False)
            prompt = self.prompt_template.format(json_data=json_data_str)
            
            logger.info("Enviando dados para classificação múltipla...")
            response = self.model.generate_content(prompt)
            
            if response.text:
                cleaned_json_str = self._clean_json_response(response.text)
                classifications_data = json.loads(cleaned_json_str)
                # Garante que seja uma lista e remove duplicatas
                classifications = sorted(list(set(classifications_data.get("classificacoes", ["NÃO CLASSIFICADO"]))))
                invoice_json["classificacoes_despesa"] = classifications
                logger.info(f"Despesas classificadas como: {classifications}")
            else:
                invoice_json["classificacoes_despesa"] = ["NÃO CLASSIFICADO"]
                logger.warning("API não retornou uma classificação.")

        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar JSON da resposta da API: {str(e)}")
            invoice_json["classificacoes_despesa"] = [f"ERRO DE DECODIFICAÇÃO JSON"]
        except Exception as e:
            logger.error(f"Erro durante a classificação: {str(e)}")
            invoice_json["classificacoes_despesa"] = [f"ERRO NA CLASSIFICAÇÃO"]
            
        return invoice_json

if __name__ == "__main__":
    # Caminho para o PDF de exemplo
    pdf_path = "C:\\Users\\BrenoHabib.DESKTOP-0I3JBOF\\Documentos\\Estudos\\Códigos\\PraticaEngSoftware\\media\\1000211448.pdf"

    # 1. Instancia e executa o agente de extração
    extractor_agent = extraction.invoice_extractor.PDFExtractorAgent()
    extracted_data = extractor_agent.extract_pdf_to_json(pdf_path)

    # Verifica se a extração foi bem-sucedida antes de classificar
    if "error" not in extracted_data:
        # 2. Instancia e executa o agente de classificação
        classifier_agent = ExpenseClassifierAgent()
        final_result = classifier_agent.classify_expense(extracted_data)
    else:
        # Se houve erro na extração, o resultado final é o próprio erro
        final_result = extracted_data

    # 3. Imprime o JSON final, agora com a classificação
    print(json.dumps(final_result, indent=2, ensure_ascii=False))