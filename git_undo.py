import sqlite3
import datetime
import subprocess
import argparse
import os

CREATE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME NOT NULL,  -- Timestamp of the snapshot
    description TEXT              -- Description of the snapshot (optional)
);


"""

CREATE_REFS = """
CREATE TABLE IF NOT EXISTS refs (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,  -- Foreign key to Snapshot
    ref_name TEXT NOT NULL,       -- Name of the ref (branch or tag)
    commit_hash TEXT NOT NULL,    -- Commit hash for the ref at this snapshot
    FOREIGN KEY (snapshot_id) REFERENCES Snapshot(id)
);
"""

CREATE_HEAD = """
CREATE TABLE IF NOT EXISTS head (
    id INTEGER PRIMARY KEY,
    snapshot_id INTEGER NOT NULL,  -- Foreign key to Snapshot
    ref_name TEXT NOT NULL,    -- Commit hash for the ref at this snapshot
    FOREIGN KEY (snapshot_id) REFERENCES Snapshot(id)
);
"""


class Snapshot:
    def __init__(self, id, timestamp, description, refs):
        self.id = id
        self.timestamp = timestamp
        self.description = description
        self.refs = refs

    def __eq__(self, other):
        if isinstance(other, Snapshot):
            return (
                self.id == other.id
                and self.timestamp == other.timestamp
                and self.description == other.description
                and self.refs == other.refs
            )

    @classmethod
    def record(cls):
        # Capture the snapshot, including all refs and HEAD
        git_command = "git for-each-ref --format='%(refname) %(objectname)'"
        process = subprocess.Popen(git_command, shell=True, stdout=subprocess.PIPE)
        output, _ = process.communicate()
        refs = [line.decode("utf-8").strip().split() for line in output.splitlines()]

        head_command = "git symbolic-ref HEAD"
        process = subprocess.Popen(head_command, shell=True, stdout=subprocess.PIPE)
        output, _ = process.communicate()
        head_ref = output.decode("utf-8").strip()

        snapshot = cls(0, "", "", refs + [("HEAD", head_ref)])
        return snapshot

    def save(self, conn):
        # Save the snapshot to the database
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO snapshots (timestamp, description) VALUES (?, ?)",
            (timestamp, self.description),
        )
        snapshot_id = cursor.lastrowid
        self.id = snapshot_id
        for ref_name, commit_hash in self.refs:
            cursor.execute(
                "INSERT INTO refs (snapshot_id, ref_name, commit_hash) VALUES (?, ?, ?)",
                (snapshot_id, ref_name, commit_hash),
            )
        cursor.execute(
            "INSERT INTO head (snapshot_id, ref_name) VALUES (?, ?)",
            (snapshot_id, self.refs[-1][1]),
        )
        conn.commit()

    @classmethod
    def load(cls, conn, snapshot_id):
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, description FROM snapshots WHERE id = ?",
            (snapshot_id,),
        )
        snapshot_data = cursor.fetchone()

        if snapshot_data is None:
            return None

        id, timestamp, description = snapshot_data
        cursor.execute(
            "SELECT ref_name, commit_hash FROM refs WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        refs_data = cursor.fetchall()
        refs = [(ref[0], ref[1]) for ref in refs_data]

        return cls(id, timestamp, description, refs)

    @staticmethod
    def load_all(conn):
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM snapshots ORDER BY id DESC")
        snapshot_ids = [row[0] for row in cursor.fetchall()]
        return [Snapshot.load(conn, snapshot_id) for snapshot_id in snapshot_ids]

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
            line.decode("utf-8").strip()
            for line in subprocess.check_output(
                "git for-each-ref --format='%(refname)'", shell=True
            ).splitlines()
        ]
        for ref in all_refs:
            if ref not in current_refs:
                git_command = f"git update-ref -d {ref}"
                subprocess.check_output(git_command, shell=True)


def get_head():
    head_command = "git symbolic-ref HEAD"
    process = subprocess.Popen(head_command, shell=True, stdout=subprocess.PIPE)
    output, _ = process.communicate()
    head_ref = output.decode("utf-8").strip()
    return head_ref


def get_reflog_message():
    git_command = "git reflog --format=%gs -n 1 HEAD"
    process = subprocess.Popen(git_command, shell=True, stdout=subprocess.PIPE)
    output, _ = process.communicate()
    reflog_message = output.decode("utf-8").strip()
    return reflog_message


def install_hooks(path="git_undo.py"):
    base_git_dir = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], universal_newlines=True
    ).strip()

    # List of Git hooks to install
    hooks_to_install = [
        "post-applypatch",
        "post-checkout",
        "post-commit",
        "post-merge",
        "post-rewrite",
        "pre-auto-gc",
        "reference-transaction",
    ]

    # Iterate through the list of hooks and install them
    for hook in hooks_to_install:
        hook_path = os.path.join(base_git_dir, ".git", "hooks", hook)
        with open(hook_path, "w") as hook_file:
            hook_file.write(
                f"""#!/bin/sh
DIR=$(git rev-parse --show-toplevel)
cd $DIR || exit
python3 {path} record || echo "error recording snapshot"
"""
            )
        os.chmod(hook_path, 0o755)


if __name__ == "__main__":
    install_hooks()


def record_snapshot(conn, description=None):
    try:
        description = get_reflog_message()
    except subprocess.CalledProcessError as e:
        print("Error getting reflog message:", e)
        return None

    cursor = conn.cursor()
    try:
        # Connect to the SQLite database

        # Get the current timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Insert a new snapshot record
        cursor.execute(
            "INSERT INTO snapshots (timestamp, description) VALUES (?, ?)",
            (timestamp, description),
        )
        snapshot_id = cursor.lastrowid  # Get the ID of the inserted snapshot

        # Capture and record all refs from the Git repository
        git_command = "git for-each-ref --format='%(refname) %(objectname)'"
        process = subprocess.Popen(git_command, shell=True, stdout=subprocess.PIPE)
        output, _ = process.communicate()
        refs = [line.decode("utf-8").strip().split() for line in output.splitlines()]

        # get HEAD
        git_command = "git rev-parse HEAD"
        process = subprocess.Popen(git_command, shell=True, stdout=subprocess.PIPE)
        output, _ = process.communicate()
        head = output.decode("utf-8").strip()

        for ref_name, commit_hash in refs:
            cursor.execute(
                "INSERT INTO refs (snapshot_id, ref_name, commit_hash) VALUES (?, ?, ?)",
                (snapshot_id, ref_name, commit_hash),
            )

        cursor.execute(
            "INSERT INTO head (snapshot_id, ref_name) VALUES (?, ?)",
            (snapshot_id, get_head()),
        )

        # Commit the changes and close the connection
        conn.commit()
        conn.close()

        return snapshot_id  # Return the ID of the new snapshot

    except sqlite3.Error as e:
        print("Error recording snapshot:", e)
        return None
    except subprocess.CalledProcessError as e:
        print("Error recording snapshot:", e)
        return None


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

    except sqlite3.Error as e:
        print("Error restoring snapshot:", e)
    except subprocess.CalledProcessError as e:
        print("Error restoring snapshot:", e)
    except ValueError as e:
        print("Error restoring snapshot:", e)


def open_memory_db():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute(CREATE_SNAPSHOTS)
    cursor.execute(CREATE_REFS)
    cursor.execute(CREATE_HEAD)
    conn.commit()
    return conn


def open_db():
    git_repository_path = subprocess.check_output(
        "git rev-parse --show-toplevel", shell=True
    )
    # add '.git/git-undo/'
    db_dir = os.path.join(
        git_repository_path.decode("utf-8").strip(), ".git", "git-undo"
    )
    os.makedirs(db_dir, exist_ok=True)
    database_path = os.path.join(db_dir, "snapshots.db")
    conn = sqlite3.connect(database_path)
    # Create the tables if they don't already exist
    cursor = conn.cursor()
    cursor.execute(CREATE_SNAPSHOTS)
    cursor.execute(CREATE_REFS)
    cursor.execute(CREATE_HEAD)
    cursor.execute("PRAGMA journal_mode=WAL")
    conn.commit()

    return conn


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
        conn = open_db()
        record_snapshot(conn)
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


if __name__ == "__main__":
    parse_args()
