from git_undo import Snapshot
import time
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
    repo_path = tempfile.mkdtemp()
    subprocess.check_call(["git", "init", repo_path])
    repo = pygit2.Repository(repo_path)

    # install hooks
    path = "python3 " + os.path.dirname(os.path.realpath(__file__)) + "/git_undo.py"
    git_undo.install_hooks(repo, path)
    return repo


def delete(repo):
    subprocess.check_call(["rm", "-rf", repo.workdir])


def test_basic_snapshot():
    repo = setup()
    subprocess.check_call(
        ["git", "commit", "--allow-empty", "-am", "test"], cwd=repo.workdir
    )
    all_snapshots = Snapshot.load_all(repo)
    # um not sure if I agree with this? why 2 snapshots?
    assert len(all_snapshots) == 2
    assert all_snapshots[0].head == "refs/heads/main"

    delete(repo)


def add_file(repo, filename, contents):
    with open(os.path.join(repo.workdir, filename), "w") as f:
        f.write(contents)
    subprocess.check_call(["git", "add", filename], cwd=repo.workdir)


def test_accurate_restore():
    repo = setup()
    subprocess.check_call(
        ["git", "commit", "--allow-empty", "-am", "initial commit"], cwd=repo.workdir
    )
    add_file(repo, "a.txt", "aaaaa")
    subprocess.check_call(["git", "commit", "-m", "a.txt"], cwd=repo.workdir)
    # wait a moment
    snapshot_id = Snapshot.load_all(repo)[0].id

    add_file(repo, "b.txt", "bbbbb")
    subprocess.check_call(["git", "commit", "-m", "b.txt"], cwd=repo.workdir)

    git_undo.restore_snapshot(repo, snapshot_id)

    # make sure that "b.txt" is gone
    assert not os.path.exists(os.path.join(repo.workdir, "b.txt")), "b.txt still exists"


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
