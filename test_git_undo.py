from git_undo import Snapshot
import subprocess
import string
import os
import tempfile
import git_undo
import pygit2


def make_git_commands():
    # make commits, make a branch, reset --hard at some point
    return [
        "git commit --allow-empty -m 'a'",
        "git checkout -b test",
        "git commit --allow-empty -m 'b'",
        "git checkout main",
        "git reset --hard test",
    ]


def setup():
    # make git dir
    tmpdir = tempfile.TemporaryDirectory(dir="/tmp")
    repo_path = tmpdir.name
    subprocess.check_call(["git", "init", repo_path])
    repo = pygit2.Repository(repo_path)

    # install hooks
    path = os.path.dirname(os.path.realpath(__file__)) + "/git_undo.py"
    git_undo.install_hooks(repo, path)

    return repo, tmpdir


def test_basic_snapshot():
    repo, _tmpdir = setup()
    subprocess.check_call(
        ["git", "commit", "--allow-empty", "-am", "test"], cwd=repo.workdir
    )
    commit_id = git_undo.record_snapshot(repo)
    snapshot = Snapshot.load(repo, commit_id)
    assert snapshot.head == "refs/heads/main"
    all_snapshots = Snapshot.load_all(repo)
    # not sure 3 is right
    assert len(all_snapshots) == 3


# todo: test that restoring most recent snapshot is a no-op

# def test_successive_snapshots():
#    return
#    git_commands = make_git_commands()
#    # Invariant 2: No two successive snapshots should be identical
#    # assert that repo_path exists
#    subprocess.check_call(["git", "init", repo_path])
#    assert os.path.exists(repo_path)
#
#    for command in git_commands:
#        subprocess.check_call(command, cwd=repo_path)
#        snapshots = Snapshot.load_all(conn)
#        if len(snapshots) >= 2:
#            assert snapshots[0] != snapshots[1], "successive snapshots are identical"
#
#    snapshots = Snapshot.load_all(conn)
