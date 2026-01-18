#!/usr/bin/env python3
"""Test de conexion directa a Azure OpenAI"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from openai import AzureOpenAI

endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
api_key = os.getenv('AZURE_OPENAI_API_KEY')
api_version = os.getenv('AZURE_OPENAI_API_VERSION')
deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT_CHAT')

print(f'Endpoint: {endpoint}')
print(f'API Version: {api_version}')
print(f'Deployment: {deployment}')
print(f'API Key: {api_key[:8]}...' if api_key else 'API Key: NOT SET')
print()

try:
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version
    )
    
    print('Enviando solicitud...')
    response = client.chat.completions.create(
        model=deployment,
        messages=[{'role': 'user', 'content': 'Responde solo con: OK'}],
        max_tokens=10
    )
    print('SUCCESS:', response.choices[0].message.content)
except Exception as e:
    print('ERROR:', type(e).__name__)
    print(str(e))
