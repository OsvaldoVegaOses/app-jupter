"""Manual smoke-test for Azure transcription (diarize model requires chunking_strategy).

Note: This is an integration script, not a unit test. It is guarded by __main__ so
pytest collection won't execute it.
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, ".")

from app.settings import load_settings


def main() -> int:
    settings = load_settings()

    audio_files = list(Path("data/projects/nubeweb/audio/raw").glob("*.m4a"))
    audio_files.sort(key=lambda x: x.stat().st_size)
    if not audio_files:
        print("No audio files found under data/projects/nubeweb/audio/raw (*.m4a).")
        return 1

    audio_file = audio_files[0]

    deployment = "gpt-4o-transcribe-diarize"
    endpoint = "https://eastus2.api.cognitive.microsoft.com"
    api_version = "2025-03-01-preview"

    url = f"{endpoint}/openai/deployments/{deployment}/audio/transcriptions?api-version={api_version}"

    print("Testing Azure Transcription - WITH chunking_strategy")
    print(f"File: {audio_file.name} ({audio_file.stat().st_size / (1024 * 1024):.1f} MB)")

    file_bytes = audio_file.read_bytes()

    headers = {"Authorization": f"Bearer {settings.azure.api_key}"}

    # chunking_strategy='auto' is required for diarize model.
    files = {"file": (audio_file.name, file_bytes, "audio/mp4")}
    data = {
        "model": deployment,
        "chunking_strategy": "auto",
    }

    with httpx.Client(timeout=httpx.Timeout(900.0, connect=60.0, read=600.0)) as client:
        resp = client.post(url, files=files, data=data, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:1200]}")
        if resp.status_code != 200:
            return 1

        result = resp.json()
        print("\nSUCCESS!")
        print(f"Text: {str(result.get('text', ''))[:300]}...")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
