#!/usr/bin/env python3
"""
Fix User.objects.create_user calls to have unique usernames.
"""
import re
from pathlib import Path

test_dir = Path("speech_processing/tests")

# Counter for unique usernames
counter = 1

for test_file in test_dir.glob("test_*.py"):
    content = test_file.read_text()

    # Replace all username="testuser" with unique usernames
    def replace_username(match):
        global counter
        replacement = f'username="testuser{counter}"'
        counter += 1
        return replacement

    content = re.sub(r'username="testuser"', replace_username, content)

    test_file.write_text(content)
    print(f"Fixed {test_file} - replaced usernames")

print(f"Done! Created {counter-1} unique usernames")
