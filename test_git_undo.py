from hypothesis import strategies as st, given
from git_undo import Snapshot
import subprocess
import string
import os
import tempfile
import sqlite3
import git_undo


@st.composite
def git_command_strategy(draw):
    # List of Git commands and their associated options.
    git_commands = [
        "git commit --allow-empty",
        "git commit --allow-empty",
        "git commit --allow-empty",
        "git commit --allow-empty",
        "git reset --hard HEAD^",
        "git reset --hard HEAD^^",
        "git checkout -b",
        "git checkout",
        "git branch -D",
    ]

    # Randomly select a Git command.

    command_list = ["git commit --allow-empty -m start".split()]
    branches = []

    while len(command_list) < 10:
        git_command = draw(st.sampled_from(git_commands))
        options = []

        if "commit" in git_command:
            commit_message = draw(
                st.text(min_size=10, max_size=10, alphabet=string.ascii_letters)
            )
            options = ["-m", commit_message]
        elif "checkout -b" in git_command:
            branch_name = draw(
                st.text(min_size=10, max_size=10, alphabet=string.ascii_letters)
            )
            branches.append(branch_name)
            options = [branch_name]
        elif "checkout" in git_command:
            if len(branches) == 0:
                continue
            branch_name = draw(st.sampled_from(branches))
            options = [branch_name]
        elif "branch -D" in git_command:
            if len(branches) == 0:
                continue
            branch_name = draw(st.sampled_from(branches))
            branches.remove(branch_name)
            options = [branch_name]

        command_list.append(git_command.split() + options)

    return command_list


def setup():
    # make git dir
    tmpdir = tempfile.TemporaryDirectory(dir="/tmp")
    repo_path = tmpdir.name
    subprocess.check_call(["git", "init", repo_path])

    # install hooks
    path = os.path.dirname(os.path.realpath(__file__)) + "/git_undo.py"
    git_undo.install_hooks(path)

    # make in memory sqlite
    return repo_path, git_undo.open_memory_db()


@given(git_commands=git_command_strategy())
def test_successive_snapshots(git_commands):
    # Invariant 2: No two successive snapshots should be identical
    repo_path, conn = setup()
    # assert that repo_path exists
    subprocess.check_call(["git", "init", repo_path])
    assert os.path.exists(repo_path)

    for command in git_commands:
        try:
            subprocess.check_call(command, cwd=repo_path)
        except subprocess.CalledProcessError:
            if "reset" in command or "branch" in command:
                pass
            else:
                raise
        snapshots = Snapshot.load_all(conn)
        if len(snapshots) >= 2:
            assert snapshots[0] != snapshots[1], "successive snapshots are identical"

    snapshots = Snapshot.load_all(conn)
