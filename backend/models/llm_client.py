# models/llm_client.py - Shared Ollama LLM Client

from ollama import Client


class LLMClient:
    """
    Singleton LLM client for Ollama
    Shared by all agents
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = Client(host='http://localhost:11434')
            cls._instance.model = 'llama3.2:8b'
            print("[LLMClient] Connected to Ollama")
        return cls._instance

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        """
        Call Ollama LLM

        Args:
            prompt: The prompt to send
            temperature: Randomness (0.0-1.0)

        Returns:
            LLM response text
        """
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        'role': 'system',
                        'content': 'You are a helpful service engineering assistant.'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                options={
                    'temperature': temperature,
                    'num_predict': 2000
                }
            )
            return response['message']['content']

        except Exception as e:
            print(f"[LLMClient] Error: {e}")
            raise Exception(f"Failed to connect to Ollama. Make sure it's running: {e}")