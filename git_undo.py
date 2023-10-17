import datetime
import subprocess
import argparse
import os
import time


def check_output(cmd, **kwargs):
    is_shell = type(cmd) is str
    # if is_shell:
    #    print(f"Running command: '{cmd}'")
    # else:
    #    print(f"running command: '{' '.join(cmd)}'")
    return (
        subprocess.check_output(cmd, shell=is_shell, **kwargs).decode("utf-8").strip()
    )


def snapshot_head():
    head_command = "git symbolic-ref HEAD"
    process = subprocess.Popen(head_command, shell=True, stdout=subprocess.PIPE)
    output, _ = process.communicate()
    return output.decode("utf-8").strip()


def snapshot_refs():
    output = check_output(["git", "for-each-ref", "--format=%(refname) %(objectname)"])
    refs = [line.strip().split() for line in output.splitlines()]
    # remove any remote refs
    refs = [ref for ref in refs if not ref[0].startswith("refs/remotes/")]
    # remove any git-undo refs
    refs = [ref for ref in refs if not ref[0].startswith("refs/heads/git-undo")]
    return refs


def add_undo_entry(tree, message, index_commit, workdir_commit):
    undo_commit = read_branch("refs/heads/git-undo")
    if undo_commit:
        commit = check_output(
            [
                "git",
                "-c",
                "user.name=git-undo",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "user.email=undo@example.com",
                "commit-tree",
                tree,
                "-m",
                message,
                "-p",
                undo_commit,
                "-p",
                index_commit,
                "-p",
                workdir_commit,
            ],
            stderr=subprocess.PIPE,
        )
        check_output(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "branch",
                "-f",
                "git-undo",
                commit,
            ]
        )
    else:
        commit = check_output(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "user.name=git-undo",
                "-c",
                "user.email=undo@example.com",
                "commit-tree",
                tree,
                "-m",
                message,
                "-p",
                index_commit,
                "-p",
                workdir_commit,
            ],
            stderr=subprocess.PIPE,
        )

        check_output(
            ["git", "-c", "core.hooksPath=/dev/null", "branch", "git-undo", commit]
        )
    return commit


def make_commit(tree):
    date = datetime.datetime(1970, 1, 1, 0, 0, 0)
    return check_output(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.name=git-undo",
            "-c",
            "user.email=undo@example.com",
            "commit-tree",
            tree,
            "-m",
            f"snapshot",
        ],
        env={
            "GIT_AUTHOR_DATE": date.isoformat(),
            "GIT_COMMITTER_DATE": date.isoformat(),
        },
    )


def snapshot_index():
    index_filename = os.path.join(git_dir(), ".git", "index")
    our_index = os.path.join(git_dir(), ".git", "undo-index")
    check_output(["cp", index_filename, our_index])
    tree = check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "write-tree"],
        env={
            "GIT_INDEX_FILE": our_index,
        },
    )
    return tree, make_commit(tree)


def snapshot_workdir(index_commit):
    our_index = os.path.join(git_dir(), ".git", "undo-index")
    env = {
        "GIT_INDEX_FILE": our_index,
    }
    check_output(["git", "-c", "core.hooksPath=/dev/null", "add", "-u"], env=env)
    tree = check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "write-tree"], env=env
    )
    os.remove(our_index)
    return tree, make_commit(tree)


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
    def record(cls):
        index_tree, index_commit = snapshot_index()
        workdir_tree, workdir_commit = snapshot_workdir(index_commit)
        return cls(
            id=None,
            message=get_message(),
            refs=snapshot_refs(),
            head=snapshot_head(),
            index_commit=index_commit,
            workdir_commit=workdir_commit,
            index_tree=index_tree,
            workdir_tree=workdir_tree,
        )

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

    def save(self):

        message = self.format()

        last_commit = read_branch("refs/heads/git-undo")
        if last_commit:
            last_message = check_output(
                ["git", "log", "-1", "--format=%B", last_commit]
            )
            if last_message == message:
                print("No changes to save")
                return

        add_undo_entry(
            message=message,
            tree=self.workdir_tree,
            index_commit=self.index_commit,
            workdir_commit=self.workdir_commit,
        )

    @classmethod
    def load(cls, commit_id):
        git_command = f"git log {commit_id} --format=%B -n 1"
        message = check_output(git_command)

        # parse message
        lines = message.splitlines()
        lines = [line.strip() for line in lines]

        # pop things off beginning
        format_version = lines.pop(0)
        assert format_version == "FormatVersion: 1"
        timestamp = lines.pop(0)
        assert timestamp.startswith("Timestamp: ")
        timestamp = timestamp.split()[1].strip()

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

        refs = {}

        while lines:
            ref = lines.pop(0)
            ref_name, sha1 = ref.split(":")
            refs[ref_name.strip()] = sha1.strip()

        return cls(
            id=commit_id,
            message=message,
            refs=refs,
            head=head,
            index=index,
            workdir=workdir,
        )

    def restore(self):
        # Restore the snapshot by checking out each ref to the respective commit hash
        for ref_name, commit_hash in self.refs:
            git_command = f"git update-ref {ref_name} {commit_hash}"
            subprocess.run(git_command, shell=True)
        head_ref = self.refs[-1][0]
        reason = "[git-undo] restored from snapshot {}".format(self.id)
        subprocess.check_call(["git", "symbolic-ref", "HEAD", head_ref, "-m", reason])
        current_refs = [ref[0] for ref in self.refs]
        all_refs = [
            line.strip()
            for line in check_output(
                "git for-each-ref --format='%(refname)'"
            ).splitlines()
        ]
        for ref in all_refs:
            if ref not in current_refs:
                git_command = f"git update-ref -d {ref}"
                subprocess.check_call(git_command)


def get_head():
    head_command = "git symbolic-ref HEAD"
    process = subprocess.Popen(head_command, shell=True, stdout=subprocess.PIPE)
    output, _ = process.communicate()
    head_ref = output.decode("utf-8").strip()
    return head_ref


def read_branch(branch):
    try:
        return check_output(["git", "rev-parse", branch])
    except subprocess.CalledProcessError:
        return None


def git_dir():
    return check_output("git rev-parse --show-toplevel")


def install_hooks(path="git_undo.py"):
    base_git_dir = git_dir()
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
        hook_path = os.path.join(base_git_dir, ".git", "hooks", hook)
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


if __name__ == "__main__":
    install_hooks()


def record_snapshot():
    snapshot = Snapshot.record()
    snapshot.save()


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


def restore_snapshot(conn, snapshot_id):
    if not index_clean():
        print("Error: The index is not clean. Please commit or stash your changes.")
        return

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT timestamp, description FROM snapshots WHERE id = ?", (snapshot_id,)
        )
        snapshot_data = cursor.fetchone()

        if not snapshot_data:
            print("Snapshot with ID {} not found.".format(snapshot_id))
            return

        timestamp, description = snapshot_data

        # Get the list of all refs using git for-each-ref
        git_command = "git for-each-ref --format='%(refname)'"
        process = subprocess.Popen(git_command, shell=True, stdout=subprocess.PIPE)
        output, _ = process.communicate()
        all_refs = [line.decode("utf-8").strip() for line in output.splitlines()]

        # Restore the snapshot by checking out each ref to the respective commit hash
        cursor.execute(
            "SELECT ref_name, commit_hash FROM refs WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        refs_data = cursor.fetchall()

        for ref_name, commit_hash in refs_data:
            git_command = "git update-ref {} {}".format(ref_name, commit_hash)
            subprocess.run(git_command, shell=True)

        cursor.execute(
            "SELECT ref_name FROM head WHERE snapshot_id = ?", (snapshot_id,)
        )
        head_data = cursor.fetchone()

        if head_data:
            head_ref = head_data[0]
            reason = "[git-undo] restored from snapshot {}".format(snapshot_id)
            subprocess.check_call(
                ["git", "symbolic-ref", "HEAD", head_ref, "-m", reason]
            )
        else:
            raise ValueError("No head ref found for snapshot {}".format(snapshot_id))

        current_ref_names = set([x[0] for x in refs_data])
        for ref in all_refs:
            if ref not in current_ref_names:
                git_command = "git update-ref -d {}".format(ref)
                subprocess.check_output(git_command, shell=True)

        print(
            "Restored snapshot (ID: {}) created at {} with description: {}".format(
                snapshot_id, timestamp, description
            )
        )

    except subprocess.CalledProcessError as e:
        print("Error restoring snapshot:", e)
    except ValueError as e:
        print("Error restoring snapshot:", e)


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
    restore_parser.add_argument("snapshot_id", type=int, help="Snapshot ID to restore")

    args = parser.parse_args()

    if args.subcommand == "record":
        record_snapshot()
    elif args.subcommand == "undo":
        undo_snapshot()
    elif args.subcommand == "init":
        install_hooks()
    elif args.subcommand == "restore":
        if args.snapshot_id:
            conn = open_db()
            restore_snapshot(conn, args.snapshot_id)
        else:
            print("Snapshot ID is required for the 'restore' subcommand.")
    else:
        print("Use 'record' or 'undo' as subcommands.")


class LockFile:
    def __init__(self):
        self.lockfile_path = os.path.join(git_dir(), ".git", "git-undo.lock")

    def __enter__(self):
        if os.path.exists(self.lockfile_path):
            raise FileExistsError(
                f"Lock file {self.lockfile_path} already exists. Another process may be using it."
            )
        with open(self.lockfile_path, "w") as lockfile:
            lockfile.write("Lock")

    def __exit__(self, exc_type, exc_value, traceback):
        os.remove(self.lockfile_path)


def get_git_command():
    ppid = os.getppid()

    try:
        gpid = check_output(["ps", "-o", "ppid=", "-p", str(ppid)])
        output = check_output(["ps", "-o", "command=", "-p", str(gpid)])
        parts = output.split()
        parts[0] = os.path.basename(parts[0])
        return " ".join(parts)
    except subprocess.CalledProcessError:
        return None


def get_reflog_message():
    git_command = "git reflog --format=%gs -n 1 HEAD"
    process = subprocess.Popen(git_command, shell=True, stdout=subprocess.PIPE)
    output, _ = process.communicate()
    reflog_message = output.decode("utf-8").strip()
    return reflog_message


def get_message():
    command = get_git_command()
    if command is not None and command[:3] == "git":
        return command
    return get_reflog_message()


if __name__ == "__main__":
    start = time.time()
    try:
        with LockFile():
            parse_args()
    except FileExistsError as _:
        pass
    elapsed = time.time() - start
    print(f"Time taken: {elapsed:.2f}s")
