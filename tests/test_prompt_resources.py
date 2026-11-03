import hashlib
import pytest
from backend.prompts import load_prompt

@pytest.mark.parametrize("name,expected",[('assessment_synthesis.txt', '9b39863d0339a88e2c5ec63b16d03de1bf48a3e8fb8027d4821f0bcafa8d0fce'), ('knowledge_prompt.txt', '59ee6089ef29eeb83253c18df0b15467c497862edf5d63716b983a31b47ed3e3'), ('knowledge_office_prompt.txt', '18d28a445eb909cae426f68212ad1fb3ae8b6c9be74ac4b94f29ee11dbee0c04'), ('assessment_extraction.txt', '38afb3f0f002d048c5efd59aefde838b98e29c287983bdb7e4bd9c2a2d226769')])
def test_prompt_content_is_preserved(name,expected):
    assert hashlib.sha256(load_prompt(name).encode()).hexdigest()==expected

@pytest.mark.parametrize("name",["../secrets","/absolute","", "nested/file.txt"])
def test_prompt_loader_rejects_paths(name):
    with pytest.raises(ValueError): load_prompt(name)
