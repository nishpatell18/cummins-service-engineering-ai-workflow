# models/llm_client.py
# Gemma 3 via Ollama — open-source, vision-capable.
# License: Google Gemma Terms of Use — permits commercial use.
# Singleton shared by all agents.

from ollama import Client
import base64, os


class LLMClient:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = Client(host='http://localhost:11434')
            cls._instance.model  = 'gemma3:latest'
            print(f"[LLMClient] Connected to Ollama — model: {cls._instance.model}")
        return cls._instance

    def generate(self, prompt: str, temperature: float = 0.2,
                 image_paths: list = None) -> str:
        """
        Call Gemma 3.
        image_paths: optional list of local file paths — Gemma 3 will analyze them.
        """
        try:
            user_msg = {'role': 'user', 'content': prompt}

            if image_paths:
                encoded = []
                for path in image_paths:
                    if os.path.exists(path):
                        with open(path, 'rb') as f:
                            encoded.append(base64.b64encode(f.read()).decode('utf-8'))
                        print(f"[LLMClient] Attached: {os.path.basename(path)}")
                if encoded:
                    user_msg['images'] = encoded

            response = self.client.chat(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': 'You are a Cummins X15 field service assistant.'},
                    user_msg
                ],
                options={'temperature': temperature, 'num_predict': 2000}
            )
            return response['message']['content']

        except Exception as e:
            print(f"[LLMClient] Error: {e}")
            raise Exception(f"Failed to connect to Ollama. Make sure it's running: {e}")
