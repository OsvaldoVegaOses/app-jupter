import sys
from unittest.mock import MagicMock
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from app.documents import read_paragraph_records

class MockParagraph:
    def __init__(self, text):
        self.text = text

class MockDocument:
    def __init__(self, paragraphs):
        self.paragraphs = [MockParagraph(p) for p in paragraphs]

# Mocking docx.Document
import app.documents
orig_Document = app.documents.Document

def mock_document_factory(path):
    if "test_simple.docx" in str(path):
        return MockDocument([
            "00:00:02 Entrevistador",
            "¿Cuál es su nombre?",
            "00:00:10 Entrevistado",
            "Me llamo Juan."
        ])
    return MockDocument([])

app.documents.Document = mock_document_factory

def test_stateful_diarization():
    records = read_paragraph_records("test_simple.docx")
    
    assert len(records) == 2
    
    # 1. Question should be interviewer
    assert records[0].text == "¿Cuál es su nombre?"
    assert records[0].speaker == "interviewer"
    
    # 2. Answer should be interviewee
    assert records[1].text == "Me llamo Juan."
    assert records[1].speaker == "interviewee"

if __name__ == "__main__":
    try:
        test_stateful_diarization()
        print("Test Passed!")
    except AssertionError as e:
        print(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
