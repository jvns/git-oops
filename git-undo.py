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


def get_head():
    head_command = "git symbolic-ref HEAD"
    process = subprocess.Popen(head_command, shell=True, stdout=subprocess.PIPE)
    output, _ = process.communicate()
    head_ref = output.decode("utf-8").strip()
    return head_ref


# Function to record a snapshot of all refs from a Git repository
def record_snapshot(conn, description=None):
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


def restore_snapshot(conn, snapshot_id):
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
            head_ref = head_data[1]
            git_command = "git symbolic-ref HEAD {}".format(head_ref)
            subprocess.check_output(git_command, shell=True)

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
