import datetime
import subprocess
import argparse
import os
import time

import pygit2


def check_output(cmd, **kwargs):
    is_shell = type(cmd) is str
    # if is_shell:
    #    print(f"Running command: '{cmd}'")
    # else:
    #    print(f"running command: '{' '.join(cmd)}'")
    start = time.time()
    result = (
        subprocess.check_output(cmd, shell=is_shell, **kwargs).decode("utf-8").strip()
    )
    elapsed = time.time() - start
    # print(f"Command took {elapsed:.3f} seconds: {cmd}")
    return result


def snapshot_head(repo):
    return repo.references["HEAD"].target


def snapshot_refs(repo):
    refs = [(ref, repo.references[ref].target) for ref in repo.references]
    refs = [ref for ref in refs if not ref[0].startswith("refs/remotes/")]
    refs = [ref for ref in refs if not ref[0].startswith("refs/heads/git-undo")]
    return refs


def add_undo_entry(repo, tree, message, index_commit, workdir_commit):
    parents = [index_commit, workdir_commit]
    try:
        undo_commit = repo.references["refs/heads/git-undo"]
        parents.insert(0, undo_commit.target)
    except KeyError:
        pass
    signature = pygit2.Signature("git-undo", "undo@example.com")
    return repo.create_commit(
        "refs/heads/git-undo", signature, signature, message, tree, parents
    )


def make_commit(repo, tree):
    date = datetime.datetime(1970, 1, 1, 0, 0, 0)
    signature = pygit2.Signature("git-undo", "undo@example.com", int(date.timestamp()))
    commit = repo.create_commit(
        None,
        signature,
        signature,
        "snapshot",
        tree,
        [],
    )
    return str(commit)


def snapshot_index(repo):
    tree = repo.index.write_tree(repo)
    return str(tree), make_commit(repo, str(tree))


def snapshot_workdir(repo, index_commit):
    our_index = os.path.join(repo.workdir, ".git", "undo-index")
    check_output(["cp", os.path.join(repo.path, "index"), our_index])
    env = {
        "GIT_INDEX_FILE": our_index,
    }
    check_output(["git", "-c", "core.hooksPath=/dev/null", "add", "-u"], env=env)
    index = pygit2.Index(our_index)
    tree = index.write_tree(repo)
    return tree, make_commit(repo, tree)


class Snapshot:
    def __init__(
        self,
        id,
        message,
        refs,
        head,
        index_tree,
        workdir_tree,
        index_commit,
        workdir_commit,
    ):
        self.id = id
        self.message = message
        self.refs = refs
        self.head = head
        self.index_tree = index_tree
        self.workdir_tree = workdir_tree
        self.index_commit = index_commit
        self.workdir_commit = workdir_commit

    def __eq__(self, other):
        if isinstance(other, Snapshot):
            return (
                self.refs == other.refs
                and self.head == other.head
                and self.index_commit == other.index_commit
                and self.workdir_commit == other.workdir_commit
            )

    @classmethod
    def record(cls, repo):
        index_tree, index_commit = snapshot_index(repo)
        workdir_tree, workdir_commit = snapshot_workdir(repo, index_commit)
        return cls(
            id=None,
            message=get_message(repo),
            refs=snapshot_refs(repo),
            head=snapshot_head(repo),
            index_commit=index_commit,
            workdir_commit=workdir_commit,
            index_tree=index_tree,
            workdir_tree=workdir_tree,
        )

    @classmethod
    def load_all(cls, repo):
        # get all commits from `git-undo` branch
        branch = repo.references["refs/heads/git-undo"]
        return [
            Snapshot.load(repo, x.id)
            for x in repo.walk(branch.target, pygit2.GIT_SORT_TOPOLOGICAL)
            if x.message.startswith("FormatVersion: 1")
        ]

    def format(self):
        # no newlines in message
        assert "\n" not in self.message
        return "\n".join(
            [
                f"FormatVersion: 1",
                f"Message: {self.message}",
                # todo: add undo
                f"HEAD: {self.head}",
                f"Index: {self.index_commit}",
                f"Workdir: {self.workdir_commit}",
                f"Refs:",
                *[f"{ref}: {sha1}" for ref, sha1 in self.refs],
            ]
        )

    def __str__(self):
        return self.format()

    def save(self, repo):

        message = self.format()

        last_commit = read_branch(repo, "refs/heads/git-undo")
        if last_commit:
            last_message = repo[last_commit].message
            if last_message == message:
                print("No changes to save")
                return

        return add_undo_entry(
            repo=repo,
            message=message,
            tree=self.workdir_tree,
            index_commit=self.index_commit,
            workdir_commit=self.workdir_commit,
        )

    @classmethod
    def load(cls, repo, commit_id):
        message = repo[commit_id].message

        # parse message
        lines = message.splitlines()
        lines = [line.strip() for line in lines]

        # pop things off beginning
        format_version = lines.pop(0)
        assert format_version == "FormatVersion: 1"

        message = lines.pop(0)
        assert message.startswith("Message: ")
        message = message.split()[1].strip()

        head = lines.pop(0)
        assert head.startswith("HEAD: ")
        head = head.split()[1].strip()

        index = lines.pop(0)
        assert index.startswith("Index: ")
        index = index.split()[1].strip()

        workdir = lines.pop(0)
        assert workdir.startswith("Workdir: ")
        workdir = workdir.split()[1].strip()

        ref_header = lines.pop(0)
        assert ref_header == "Refs:"

        refs = []

        while lines:
            ref = lines.pop(0)
            ref_name, sha1 = ref.split(":")
            refs.append((ref_name.strip(), sha1.strip()))

        return cls(
            id=commit_id,
            message=message,
            refs=refs,
            head=head,
            index_commit=index,
            workdir_commit=workdir,
            index_tree=None,
            workdir_tree=None,
        )

    def restore(self, repo):
        # restore workdir and index
        check_output(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "restore",
                "--source",
                self.workdir_commit,
                ".",
            ]
        )
        check_output(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "restore",
                "--source",
                self.index_commit,
                "--staged",
                ".",
            ]
        )
        repo.references.create("HEAD", self.head, force=True)
        for ref, target in self.refs:
            repo.references.create(ref, target, force=True)


def get_head():
    head_command = "git symbolic-ref HEAD"
    process = subprocess.Popen(head_command, shell=True, stdout=subprocess.PIPE)
    output, _ = process.communicate()
    head_ref = output.decode("utf-8").strip()
    return head_ref


def read_branch(repo, branch):
    try:
        return repo.references[branch].target
    except KeyError:
        return None


def install_hooks(repo, path="git_undo.py"):
    # List of Git hooks to install
    hooks_to_install = [
        "post-applypatch",
        "post-checkout",
        "pre-commit",
        "post-commit",
        "post-merge",
        "post-rewrite",
        "pre-auto-gc",
        "post-index-change",
        "reference-transaction",
    ]

    # Iterate through the list of hooks and install them
    for hook in hooks_to_install:
        hook_path = os.path.join(repo.workdir, ".git", "hooks", hook)
        with open(hook_path, "w") as hook_file:
            if hook == "reference-transaction":
                # only record when committed
                hook_file.write(
                    f"""#!/bin/sh
DIR=$(git rev-parse --show-toplevel)
cd $DIR || exit
# check if $1 = "committed"
if [ "$1" = "committed" ]; then
    python3 {path} record || echo "error recording snapshot in {hook}"
fi
        """
                )
            else:
                hook_file.write(
                    f"""#!/bin/sh
    DIR=$(git rev-parse --show-toplevel)
    cd $DIR || exit
    python3 {path} record || echo "error recording snapshot in {hook}"
    """
                )
        os.chmod(hook_path, 0o755)


def record_snapshot(repo):
    snapshot = Snapshot.record(repo)
    return snapshot.save(repo)


def restore_snapshot(repo, commit_id):
    snapshot = Snapshot.load(repo, commit_id)
    changes = calculate_diff(repo, snapshot)
    if confirm(repo, changes):
        snapshot.restore(repo)


def calculate_diff(repo, then):
    now = Snapshot.record(repo)
    now.save(repo)
    # get list of changed refs
    changes = {
        "refs": {},
        "HEAD": None,
        "workdir": None,
        "index": None,
    }

    for ref, new_target in now.refs:
        old_target = dict(then.refs).get(ref)
        if str(old_target) != str(new_target):
            changes["refs"][ref] = (old_target, new_target)

    if then.head != now.head:
        changes["HEAD"] = (then.head, now.head)
    if then.workdir_commit != now.workdir_commit:
        changes["workdir"] = (then.workdir_commit, now.workdir_commit)
    if then.index_commit != now.index_commit:
        changes["index"] = (then.index_commit, now.index_commit)
    return changes


def count_commits_between(repo, base, target):
    walker = repo.walk(target, pygit2.GIT_SORT_TOPOLOGICAL)

    # Count the number of commits between the base and old_commit
    commit_count = 0
    for commit in walker:
        if commit.id == base:
            break
        commit_count += 1

    return commit_count


def compare(repo, old_commit, new_commit):
    base = repo.merge_base(old_commit, new_commit)
    # get number of commits between base and old_commit

    old_count = count_commits_between(repo, base, old_commit)
    new_count = count_commits_between(repo, base, new_commit)

    if old_count > 0 and new_count > 0:
        return f"have diverged by {old_count} and {new_count} commits"
    elif old_count == 1:
        return f"will move forward by {old_count} commit"
    elif old_count > 1:
        return f"will move forward by {old_count} commits"
    elif new_count == 1:
        return f"will move back by {new_count} commit"
    elif new_count > 1:
        return f"will move back by {new_count} commits"
    else:
        raise Exception("should not be here")


def confirm(repo, changes):
    for ref, (old_target, new_target) in changes["refs"].items():
        print(f"{ref}:", compare(repo, old_target, new_target))

    if changes["HEAD"]:
        old_target, new_target = changes["HEAD"]
        print(f"will move from branch {old_target} to {new_target}")
    if changes["workdir"]:
        old_target, new_target = changes["workdir"]
        # ask if user wants diff
        prompt = f"Working directory will change. Show diff? [y/N] "
        if input(prompt).lower() == "y":
            subprocess.check_call(["git", "diff", new_target, old_target])

    return False


def index_clean():
    try:
        # Use the 'git status' command to check the status of the working directory and index
        git_status_command = "git status --porcelain"
        process = subprocess.Popen(
            git_status_command, shell=True, stdout=subprocess.PIPE
        )
        output, _ = process.communicate()

        # If the 'git status' command returns an empty string, both the working directory and index are clean
        return len(output.decode("utf-8").strip()) == 0

    except subprocess.CalledProcessError as e:
        print("Error checking if the index is clean:", e)
        return False


def parse_args():
    parser = argparse.ArgumentParser(description="Git Snapshot Tool")

    # Create a subparser for the 'record' subcommand
    record_parser = parser.add_subparsers(title="subcommands", dest="subcommand")
    record_parser.add_parser("record", help="Record a new snapshot")

    # Create a subparser for the 'undo' subcommand
    undo_parser = record_parser.add_parser("undo", help="Undo the last snapshot")
    init_parser = record_parser.add_parser("init", help="Install hooks")

    restore_parser = record_parser.add_parser(
        "restore", help="Restore a specific snapshot"
    )
    restore_parser.add_argument("snapshot_id", type=str, help="Snapshot ID to restore")

    args = parser.parse_args()

    repository_path = pygit2.discover_repository(".")
    repo = pygit2.Repository(repository_path)

    if args.subcommand == "record":
        record_snapshot(repo)
    elif args.subcommand == "undo":
        undo_snapshot(repo)
    elif args.subcommand == "init":
        install_hooks(repo)
    elif args.subcommand == "restore":
        if args.snapshot_id:
            restore_snapshot(repo, args.snapshot_id)
        else:
            print("Snapshot ID is required for the 'restore' subcommand.")
    else:
        print("Use 'record' or 'undo' as subcommands.")


def get_git_command():
    # todo: seems sketchy
    ppid = os.getppid()

    try:
        gpid = check_output(["ps", "-o", "ppid=", "-p", str(ppid)])
        output = check_output(["ps", "-o", "command=", "-p", str(gpid)])
        parts = output.split()
        parts[0] = os.path.basename(parts[0])
        return " ".join(parts)
    except subprocess.CalledProcessError:
        return None


def get_reflog_message(repo):
    head = repo.references.get("HEAD")
    reflog = next(head.log())
    return reflog.message


def get_message(repo):
    command = get_git_command()
    if command is not None and command[:3] == "git":
        return command
    return get_reflog_message(repo)


if __name__ == "__main__":
    start = time.time()
    parse_args()
    elapsed = time.time() - start
    print(f"Time taken: {elapsed:.2f}s")
