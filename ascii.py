import pygit2
import sys


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


def generate_ascii_diagram(repo, then_sha, now_sha):

    then = repo.get(then_sha)
    now = repo.get(now_sha)

    assert then and now, "Invalid SHA"

    # Find common ancestor
    ancestor_sha = repo.merge_base(then.id, now.id)
    ancestor = repo.get(ancestor_sha)
    assert ancestor, "Couldn't get ancestor SHA"
    if ancestor.id == then.id or ancestor.id == now.id:
        draw_line_diagram(repo, then, now, ancestor)
    else:
        draw_diverged_diagram(repo, then, now, ancestor)


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

    for i in range(max_len):
        left = then_commits[i]
        right = now_commits[i]

        left_str = (
            f"{symbol(left, then, now)}{short(left)} {left.message.strip()}"
            if left
            else " " * 44
        )
        right_str = (
            f"{symbol(right, then, now)}{short(right)} {right.message.strip()}"
            if right
            else ""
        )

        print(f"{left_str.ljust(44)} {right_str.ljust(23)}")

    print("    ┬" + " " * 43 + "┬")
    print("    ┝" + "─" * 43 + "┘")
    print("    │")
    print(f" {short(ancestor)} {ancestor.message.strip()}")


def draw_line_diagram(repo, then, now, ancestor):
    # draw a simple version in the case that the ancestor is same as then or now
    if then.id == ancestor.id:
        history = get_commits_after_ancestor(repo, now, then, include=True)
    elif now.id == ancestor.id:
        history = get_commits_after_ancestor(repo, then, now, include=True)
    else:
        raise Exception("Ancestor must be same as then or now")

    for commit in history:
        print(f"{symbol(commit, then, now)}{short(commit)} {commit.message.strip()}")


def short(commit):
    return str(commit.id)[:6]


def normalize_lengths(l, max_len):
    return [None] * (max_len - len(l)) + l


repo = pygit2.Repository(".")
generate_ascii_diagram(repo, sys.argv[1], sys.argv[2])
