from hypothesis import strategies as st, composite


@composite
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

    command_list = [git_commands[0].split()]
    branches = []

    while len(command_list) < 20:
        git_command = draw(st.sampled_from(git_commands))
        options = []

        if "reset --hard" in git_command:
            options = ["HEAD~1"]
        elif "commit" in git_command:
            commit_message = draw(st.text())
            options += ["-m", commit_message]
        elif "checkout -b" in git_command:
            branch_name = draw(st.text())
            options.append(branch_name)
            branches.append(branch_name)
        elif "checkout" in git_command:
            branch_name = draw(st.sampled_from(branches))
            options.append(branch_name)
        elif "branch -D" in git_command:
            branch_name = draw(st.sampled_from(branches))
            branches.remove(branch_name)
            options.append(branch_name)
        command_list.append(git_command.split() + options)

    return command_list
