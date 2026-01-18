"""
Test Azure API WITH chunking_strategy - it's REQUIRED for diarize model!
"""
import httpx
import sys
import json
from pathlib import Path

sys.path.insert(0, '.')
from app.settings import load_settings

settings = load_settings()

audio_files = list(Path('data/projects/nubeweb/audio/raw').glob('*.m4a'))
audio_files.sort(key=lambda x: x.stat().st_size)
audio_file = audio_files[0]

deployment = "gpt-4o-transcribe-diarize"
endpoint = "https://eastus2.api.cognitive.microsoft.com"
api_version = "2025-03-01-preview"

url = f'{endpoint}/openai/deployments/{deployment}/audio/transcriptions?api-version={api_version}'

print('Testing Azure Transcription - WITH chunking_strategy')
print(f'File: {audio_file.name} ({audio_file.stat().st_size / (1024*1024):.1f} MB)')

with open(audio_file, 'rb') as f:
    file_bytes = f.read()

headers = {'Authorization': f'Bearer {settings.azure.api_key}'}

# Test with chunking_strategy = "auto" as simple string
print('\n[Test] With chunking_strategy="auto"...')
files = {'file': (audio_file.name, file_bytes, 'audio/mp4')}
data = {
    'model': deployment,
    'chunking_strategy': 'auto',  # Required for diarize model!
}

with httpx.Client(timeout=httpx.Timeout(900.0, connect=60.0, read=600.0)) as client:
    resp = client.post(url, files=files, data=data, headers=headers)
    print(f'Status: {resp.status_code}')
    print(f'Response: {resp.text[:1200]}')
    
    if resp.status_code == 200:
        result = resp.json()
        print(f'\n✅ SUCCESS!')
        print(f'Text: {result.get("text", "")[:300]}...')
