import base64
import io
import wave
import json
from types import SimpleNamespace

# Generate 0.5s of silence WAV (16kHz, mono, 16-bit)
framerate = 16000
nframes = int(0.5 * framerate)
buf = io.BytesIO()
with wave.open(buf, 'wb') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(framerate)
    w.writeframes(b'\x00\x00' * nframes)
wav_bytes = buf.getvalue()
wav_b64 = base64.b64encode(wav_bytes).decode('ascii')

# Dummy self for bound task
class DummySelf:
    def __init__(self):
        self.request = SimpleNamespace(id='local-test')
    def update_state(self, state=None, meta=None):
        print('update_state', state, meta)

# Call the task function directly
try:
    import sys
    from pathlib import Path
    # Ensure repo root on sys.path
    repo_root = str(Path(__file__).resolve().parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from backend.celery_worker import task_transcribe_audio
except Exception as e:
    print('Import error:', e)
    raise

self = DummySelf()

print('Running local transcription task...')
# Call the original function wrapped by Celery to avoid wrapper argument issues
wrapped = getattr(task_transcribe_audio, '__wrapped__', task_transcribe_audio)
import inspect
print('task_transcribe_audio object:', task_transcribe_audio)
print('wrapped object:', wrapped)
try:
    print('wrapped signature:', inspect.signature(wrapped))
except Exception as e:
    print('Could not get signature:', e)
except Exception as e:
    print('Could not get signature:', e)

# Monkeypatch blob storage functions to avoid requiring Azure SDK in local tests
import os
# Load AZURE_STORAGE_CONNECTION_STRING from .env if present and not already set
try:
    if not os.environ.get("AZURE_STORAGE_CONNECTION_STRING"):
        env_path = Path(repo_root) / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("AZURE_STORAGE_CONNECTION_STRING"):
                        _, val = line.split("=", 1)
                        val = val.strip().strip('"').strip("'")
                        os.environ["AZURE_STORAGE_CONNECTION_STRING"] = val
                        break
except Exception:
    pass
try:
    # If an AZURE connection string is configured and FORCE_MOCK_BLOBS is not set,
    # prefer real Azure Blob Storage. Otherwise, monkeypatch to local tmp_blobs.
    use_real_azure = bool(os.environ.get("AZURE_STORAGE_CONNECTION_STRING")) and os.environ.get("FORCE_MOCK_BLOBS") != "1"
    if not use_real_azure:
        import app.blob_storage as blob_storage
        import shutil
        from pathlib import Path

        tmp_blobs_root = Path(repo_root) / "tmp_blobs"

        def fake_upload_file(container: str, blob_name: str, data: bytes, content_type: str | None = None) -> str:
            dest = tmp_blobs_root / container / blob_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
            return f"file://{dest.as_posix()}"

        def fake_upload_local_path(*, container: str, blob_name: str, file_path: str, content_type: str | None = None) -> str:
            dest = tmp_blobs_root / container / blob_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(file_path, dest)
            return f"file://{dest.as_posix()}"

        blob_storage.upload_file = fake_upload_file
        blob_storage.upload_local_path = fake_upload_local_path
        print('Blob storage monkeypatched to local tmp_blobs/')
    else:
        print('AZURE_STORAGE_CONNECTION_STRING present: using real Azure Blob Storage')
except Exception as e:
    print('Could not configure blob storage mode:', e)
if getattr(wrapped, '__self__', None) is not None:
    # bound method (Celery task wrapper); don't pass self
    # Ensure the bound task has a fake request.id and update_state to avoid Celery backend calls
    bound = getattr(wrapped, '__self__')
    try:
        bound.request = SimpleNamespace(id='local-test')
    except Exception:
        pass
    try:
        bound.update_state = lambda state=None, meta=None: print('update_state', state, meta)
    except Exception:
        pass
    res = wrapped('local-org', 'local-project', audio_base64=wav_b64, filename='silence.wav', diarize=False, language='es', ingest=False, min_chars=200, max_chars=1200, incremental=False)
else:
    res = wrapped(self, org_id='local-org', project_id='local-project', audio_base64=wav_b64, filename='silence.wav', diarize=False, language='es', ingest=False, min_chars=200, max_chars=1200, incremental=False)
print('\nResult:')
print(json.dumps(res, indent=2, ensure_ascii=False))
