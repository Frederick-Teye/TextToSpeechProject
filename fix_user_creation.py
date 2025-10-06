#!/usr/bin/env python3
"""
Fix User.objects.create_user calls formatting.
"""
import re
from pathlib import Path

test_dir = Path("speech_processing/tests")

for test_file in test_dir.glob("test_*.py"):
    content = test_file.read_text()

    # Fix broken line breaks: username="...", \n            email=
    # Should be: username="...", email=
    content = re.sub(r'(username="[^"]+"), \n\s+', r"\1, ", content)

    test_file.write_text(content)
    print(f"Fixed {test_file}")

print("Done fixing formatting")
