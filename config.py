from dataclasses import dataclass
from enum import Enum

class ModelProvider(str, Enum):
    OLLAMA = "ollama"
    GROQ = "groq"

@dataclass
class ModelConfig:
    name: str
    temperature: float
    provider: ModelProvider

llama3_2_3B = ModelConfig("llama3.2:3b", temperature=0.01, provider=ModelProvider.OLLAMA)

devstral_24B = ModelConfig("devstral:24b", temperature=0.01, provider=ModelProvider.OLLAMA)
 
gemma3_12B = ModelConfig("gemma3:12b", temperature=0.01, provider=ModelProvider.OLLAMA)

deepseek_R1_14b= ModelConfig("deepseek-r1:14b", temperature=0.01, provider=ModelProvider.OLLAMA)


class Config:
    SEED = 42
    MODEL = gemma3_12B
    OLLAMA_CONTEXT_WINDOW = 4096 # Increase to allow longer conversations but slower response
    OLLAMA_BASE_URL= "https://inference.jhingaai.com"

    class Server:
        HOST = "localhost"
        PORT = 8000
        SSE_PATH = "/sse"
        TRANSPORT = "sse"

    class Agent:
        MAX_ITERATIONS=10    