#!/usr/bin/env python3

import datetime
import subprocess
import argparse
import os
import time
import curses

import pygit2

UNDO_REF = "refs/git-undo"


def check_output(cmd, **kwargs):
    is_shell = type(cmd) is str
    # if is_shell:
    #    print(f"Running command: '{cmd}'")
    # else:
    #    print(f"running command: '{' '.join(cmd)}'")
    start = time.time()
    result = subprocess.check_output(cmd, shell=is_shell, **kwargs).decode("utf-8")
    elapsed = time.time() - start
    # print(f"Command took {elapsed:.3f} seconds: {cmd}")
    return result


def snapshot_head(repo):
    return repo.references["HEAD"].target


def snapshot_refs(repo):
    refs = [(ref, repo.references[ref].target) for ref in repo.references]
    refs = [
        ref
        for ref in refs
        if (ref[0].startswith("refs/tags/") or ref[0].startswith("refs/heads"))
    ]
    return refs


def add_undo_entry(repo, tree, message, index_commit, workdir_commit):
    parents = [index_commit, workdir_commit]
    signature = pygit2.Signature("git-undo", "undo@example.com")
    undo_ref = None
    old_target = None
    try:
        undo_ref = repo.references[UNDO_REF]
        old_target = undo_ref.target
    except KeyError:
        pass
    commit_id = repo.create_commit(None, signature, signature, message, tree, parents)
    # `repo.create_reference` says:
    # > The message for the reflog will be ignored if the reference does not
    # > belong in the standard set (HEAD, branches and remote-tracking branches)
    # > and it does not have a reflog.
    # so we need to create the reflog explicitly

    reflog_file = repo.path + "/logs/" + UNDO_REF

    # create empty file if it doesn't exist
    if not os.path.exists(reflog_file):
        open(reflog_file, "a").close()

    reflog_message = "snapshot"
    if undo_ref:
        undo_ref.set_target(commit_id, reflog_message)
    else:
        repo.create_reference(UNDO_REF, str(commit_id), message=reflog_message)


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
    our_index = os.path.join(repo.path, "undo-index")
    # it's important that we use `index.lock` instead of `index` here because
    # we're often in the middle of an index transaction when snapshotting.
    # Otherwise we'll give an incorrect impression of the current state of the index
    #
    # This is really kind of a weird thing to do (what if the transaction fails
    # and git removes the `index.lock` without moving it to `index`? But for
    # now it seems better than the alternative, which is that after the commit
    # is made, in the `reference-transaction` hook it still appears as if we're
    # using the old index.
    if os.path.exists(os.path.join(repo.path, "index.lock")):
        check_output(["cp", os.path.join(repo.path, "index.lock"), our_index])
    else:
        check_output(["cp", os.path.join(repo.path, "index"), our_index])
    index = pygit2.Index(our_index)
    tree = index.write_tree(repo)
    return str(tree), make_commit(repo, str(tree))


def snapshot_workdir(repo, index_commit):
    our_index = os.path.join(repo.path, "undo-index")
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
        refs,
        head,
        index_tree,
        workdir_tree,
        index_commit,
        workdir_commit,
    ):
        self.id = id
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
            refs=snapshot_refs(repo),
            head=snapshot_head(repo),
            index_commit=index_commit,
            workdir_commit=workdir_commit,
            index_tree=index_tree,
            workdir_tree=workdir_tree,
        )

    @classmethod
    def load_all(cls, repo):
        return [Snapshot.load(repo, x.oid_new) for x in repo.references[UNDO_REF].log()]

    def format(self):
        # no newlines in message
        return "\n".join(
            [
                f"FormatVersion: 1",
                # f"Message: {self.message}",
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

        last_commit = read_branch(repo, UNDO_REF)
        if last_commit:
            last_message = repo[last_commit].message
            if last_message == message:
                # print("No changes to save")
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

        # message = lines.pop(0)
        # assert message.startswith("Message: ")
        # message = message[len("Message: ") :]

        head = lines.pop(0)
        assert head.startswith("HEAD:")
        if len(head.split()) == 2:
            head = head.split()[1].strip()
        else:
            head = None

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
            refs=refs,
            head=head,
            index_commit=index,
            workdir_commit=workdir,
            index_tree=None,
            workdir_tree=None,
        )

    def restore(self, repo):
        try:
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
        except subprocess.CalledProcessError as e:
            print("Failed to restore workdir, can't restore snapshot")
            return
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
    if check_rebase(repo):
        return
    snapshot = Snapshot.record(repo)
    return snapshot.save(repo)


def restore_snapshot(repo, commit_id):
    snapshot = Snapshot.load(repo, commit_id)
    return snapshot.restore(repo)


def undo(repo):
    now = Snapshot.record(repo)
    now.save(repo)
    for commit in repo.references[UNDO_REF].log():
        then = Snapshot.load(repo, commit.oid_new)
        changes = calculate_diff(now, then)
        if changes["refs"] or changes["HEAD"]:
            print(f"Restoring snapshot {then.id}")
            restore_snapshot(repo, then.id)
            return


def calculate_diff(now, then):
    # get list of changed refs
    changes = {
        "refs": {},
        "HEAD": None,
        "workdir": None,
        "index": None,
    }

    for ref, new_target in now.refs:
        if ref[:10] != "refs/heads" and ref[:9] != "refs/tags":
            continue
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


def format_status(then, now):
    then_head = resolve_head(then)
    staged_diff = check_output(
        [
            "git",
            "diff",
            "--stat",
            then_head,
            then.index_commit,
        ]
    )
    unstaged_diff = check_output(
        ["git", "diff", "--stat", then.workdir_commit, then.index_commit]
    )
    result = []
    if len(staged_diff.strip()) > 0:
        result.append("Staged changes:")
        result += staged_diff.rstrip("\n").split("\n")

    if len(unstaged_diff.strip()) > 0:
        result.append("Unstaged changes:")
        result += unstaged_diff.rstrip("\n").split("\n")
    return ("git status", result)


def check_rebase(repo):
    if os.path.exists(os.path.join(repo.path, "rebase-apply")):
        return True
    if os.path.exists(os.path.join(repo.path, "rebase-merge")):
        return True
    return False


def format_changes(repo, changes, now, then):
    boxes = []
    then_head = resolve_head(then)
    for ref, (old_target, new_target) in changes["refs"].items():
        boxes.append(
            (f"{ref} changed", draw_ascii_diagram(repo, old_target, new_target))
        )

    if changes["HEAD"]:
        then_target, now_target = changes["HEAD"]
        boxes.append(
            ("current branch", [f"will move from branch {now_target} to {then_target}"])
        )
    if changes["workdir"]:
        old_workdir, new_workdir = changes["workdir"]
        boxes.append(
            (
                "diff from current workdir",
                check_output(["git", "diff", "--stat", new_workdir, old_workdir])
                .rstrip("\n")
                .split("\n"),
            )
        )

    boxes.append(format_status(then, now))
    return boxes


def resolve_head(snapshot):
    if snapshot.head.startswith("refs/"):
        return dict(snapshot.refs)[snapshot.head]
    return snapshot.head


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
    undo_parser = record_parser.add_parser("history", help="Display snapshot history")
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
    elif args.subcommand == "history":
        CursesApp(repo)
    elif args.subcommand == "undo":
        undo(repo)
    elif args.subcommand == "init":
        install_hooks(repo)
    elif args.subcommand == "restore":
        if args.snapshot_id:
            restore_snapshot(repo, args.snapshot_id)
        else:
            print("Snapshot ID is required for the 'restore' subcommand.")
    else:
        print("Use 'record' or 'undo' as subcommands.")


def get_reflog_message(repo):
    head = repo.references.get("HEAD")
    reflog = next(head.log())
    return reflog.message


def main():
    start = time.time()
    parse_args()
    elapsed = time.time() - start
    print(f"Time taken: {elapsed:.2f}s")


class CursesApp:
    def __init__(self, repo):
        self.items = Snapshot.load_all(repo)
        self.current_item = 0
        self.pad_pos = 0  # Position of the viewport in the pad (top line)
        self.repo = repo
        curses.wrapper(self.run)

    def run(self, stdscr):
        self.stdscr = stdscr
        self.setup_curses()
        self.main_loop()

    def setup_curses(self):
        curses.curs_set(0)
        self.stdscr.nodelay(1)
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)

    def main_loop(self):
        changed = True
        while True:
            if changed:
                self.refresh()
            changed = self.handle_input()

    def refresh(self):
        self.draw_details()

    def set_title(self, title):
        title = " " + title + " "
        # get screen width
        _, maxx = self.stdscr.getmaxyx()
        self.stdscr.addstr(0, (maxx - len(title)) // 2, title)

    def draw_box(self, y, width, title="", content=[]):
        if content == []:
            content = [""]
        x = 1
        height = len(content) + 2  # +2 for top and bottom borders of the box
        win = curses.newwin(height, width, y, x)
        win.box()
        # Add the title to the box
        win.addstr(0, 3, title)

        # Add content to the box
        for idx, line in enumerate(content):
            win.addstr(idx + 1, 1, line)

        return (
            win,
            y + height,
        )  # Return the y-coordinate for the next box to ensure no overlap

    def draw_details(self):
        self.stdscr.clear()
        self.stdscr.box()  # Re-draw box after clearing

        snapshot = self.items[self.current_item]
        self.set_title("back " + str(self.current_item) + ": " + str(snapshot.id)[:6])
        now = Snapshot.record(self.repo)
        now.save(self.repo)
        changes = calculate_diff(now, snapshot)
        boxes = format_changes(self.repo, changes, now, snapshot)
        self.windows = []
        y_next = 1
        for title, content in boxes:
            win, y_next = self.draw_box(y_next, width=90, title=title, content=content)
            self.windows.append(win)
        # draw all the windows
        self.stdscr.refresh()
        for win in self.windows:
            win.refresh()

    def handle_input(self):
        key = self.stdscr.getch()
        max_y, _ = self.stdscr.getmaxyx()

        if key == -1:
            # No input
            time.sleep(0.01)  # Sleep briefly to prevent 100% CPU usage
            return False
        elif key == ord("q"):
            exit()
        elif key == curses.KEY_DOWN and self.current_item < len(self.items) - 1:
            self.current_item += 1
        elif key == curses.KEY_LEFT and self.current_item < len(self.items) - 1:
            self.current_item += 1
        elif key == curses.KEY_UP and self.current_item > 0:
            self.current_item -= 1
        elif key == curses.KEY_RIGHT and self.current_item > 0:
            self.current_item -= 1
        elif key == curses.KEY_RESIZE:
            pass
        else:
            return False
        return True


def get_commits_after_ancestor(repo, commit, ancestor, include=False):
    commits = []
    while commit and commit.id != ancestor.id:
        commits.append(commit)
        if len(commit.parent_ids) > 0:
            commit = repo.get(commit.parent_ids[0])
        else:
            commit = None
    if include:
        commits.append(ancestor)
    return commits


def draw_ascii_diagram(repo, then_sha, now_sha):

    then = repo.get(str(then_sha))
    now = repo.get(str(now_sha))

    assert then and now, "Invalid SHA"

    # Find common ancestor
    ancestor_sha = repo.merge_base(then.id, now.id)
    ancestor = repo.get(ancestor_sha)
    assert ancestor, "Couldn't get ancestor SHA"
    if ancestor.id == then.id or ancestor.id == now.id:
        return draw_line_diagram(repo, then, now, ancestor)
    else:
        return draw_diverged_diagram(repo, then, now, ancestor)


def symbol(commit, then, now):
    if commit == then:
        return "➤"
    elif commit == now:
        return "★"
    else:
        return " "


def draw_diverged_diagram(repo, then, now, ancestor):
    then_commits = get_commits_after_ancestor(repo, then, ancestor)
    now_commits = get_commits_after_ancestor(repo, now, ancestor)

    max_len = max(len(then_commits), len(now_commits))

    # normalize lengths to pad out the shorter list with `None` at the beginning
    then_commits = normalize_lengths(then_commits, max_len)
    now_commits = normalize_lengths(now_commits, max_len)

    result = []
    for i in range(max_len):
        left = then_commits[i]
        right = now_commits[i]

        left_str = (
            f"{symbol(left, then, now)}{short(left)} {truncate_message(left.message)}"
            if left
            else " " * 44
        )
        right_str = (
            f"{symbol(right, then, now)}{short(right)} {truncate_message(right.message)}"
            if right
            else ""
        )

        result.append(f"{left_str.ljust(44)} {right_str.ljust(23)}")

    result.append("    ┬" + " " * 43 + "┬")
    result.append("    ┝" + "─" * 43 + "┘")
    result.append("    │")
    result.append(f" {short(ancestor)} {truncate_message(ancestor.message, 60)}")
    return result


def draw_line_diagram(repo, then, now, ancestor):
    # draw a simple version in the case that the ancestor is same as then or now
    if then.id == ancestor.id:
        history = get_commits_after_ancestor(repo, now, then, include=True)
    elif now.id == ancestor.id:
        history = get_commits_after_ancestor(repo, then, now, include=True)
    else:
        raise Exception("Ancestor must be same as then or now")

    # if there are more than 6 commits, truncate the middle
    num_omitted = len(history) - 5
    if len(history) > 6:
        history = history[:3] + [None] + history[-2:]

    return [
        f"{symbol(commit, then, now)}{short(commit)} {commit.message.strip()}"
        if commit
        else f"    ... {num_omitted} commits omitted ..."
        for commit in history
    ]


def truncate_message(message, length=34):
    message = message.strip()
    if len(message) > length:
        return message[: length - 3] + "..."
    return message


def short(commit):
    return str(commit.id)[:6]


def normalize_lengths(l, max_len):
    return [None] * (max_len - len(l)) + l


if __name__ == "__main__":
    main()
