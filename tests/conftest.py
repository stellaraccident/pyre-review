"""Shared fixtures for pyre-review tests."""

import os
import subprocess
import textwrap

import pytest


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary git repo with a main branch and a topic branch.

    Structure:
      main:  hello.py (original)
      topic/test-review:  hello.py (modified) + new_file.py (added)
    """
    repo = str(tmp_path / "repo")
    os.makedirs(repo)

    def run(*args, **kwargs):
        return subprocess.run(
            *args, capture_output=True, text=True, cwd=repo, check=True, **kwargs
        )

    # Init repo
    run(["git", "init"])
    run(["git", "config", "user.name", "Test User"])
    run(["git", "config", "user.email", "test@example.com"])

    # Create main branch with initial files
    hello_py = os.path.join(repo, "hello.py")
    with open(hello_py, "w") as f:
        f.write(textwrap.dedent("""\
            def greet(name):
                return f"Hello, {name}!"

            def main():
                print(greet("world"))

            if __name__ == "__main__":
                main()
        """))

    readme = os.path.join(repo, "README.md")
    with open(readme, "w") as f:
        f.write("# Test Project\n")

    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Initial commit"])

    # Rename default branch to main
    run(["git", "branch", "-M", "main"])

    # Create topic branch with changes
    run(["git", "checkout", "-b", "topic/test-review"])

    # Modify hello.py
    with open(hello_py, "w") as f:
        f.write(textwrap.dedent("""\
            import sys

            def greet(name):
                return f"Hello, {name}!"

            def farewell(name):
                return f"Goodbye, {name}!"

            def main():
                if "--bye" in sys.argv:
                    print(farewell("world"))
                else:
                    print(greet("world"))

            if __name__ == "__main__":
                main()
        """))

    # Add new file
    new_file = os.path.join(repo, "utils.py")
    with open(new_file, "w") as f:
        f.write(textwrap.dedent("""\
            def capitalize_words(s):
                return " ".join(w.capitalize() for w in s.split())
        """))

    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Add farewell and utils"])

    # Second commit on topic
    with open(new_file, "a") as f:
        f.write(textwrap.dedent("""\

            def reverse_string(s):
                return s[::-1]
        """))

    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Add reverse_string"])

    # Go back to main
    run(["git", "checkout", "main"])

    return repo
