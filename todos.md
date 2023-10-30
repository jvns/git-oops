problems:

- [X] index commit in snapshot is not actually immutable, that sucks (fixed)
- [X] can't do snapshots in reference-transaction or post-index-change (fix: don't run hooks)
- [X] fix snapshots inside snapshots (fix: don't run a hooks, do I still need the lockfile?)
- [X] messages don't give you the actual operation that's running
- [X] 130ms to make a recording is a bit slow (idea: pygit2?? -- for now)
- [X] lock file management feels kinda flaky
- [X] fix "ref HEAD is not a symbolic ref" during rebase
- [X] need to implement restore
- [X] no diffing in restore
- [X] bug: some snapshots are identical
- [X] switch to reflog design
- [X] bug: changes are both staged and unstaged at the same time when making a commit (solution: use `index.lock` instead of `index`)
- [X] commit is like 4 operations, reset is 3 operations (idea: implement a wrapper?)
- [X] we don't update reflog when updating HEAD / other references
- [X] snapshots in the middle of a rebase are confusing (removed them)
- [ ] feature: add a "preview" command to show what it would be like to restore a snapshot maybe?
- [ ] feature: there's no way to uninstall the hooks
- [ ] bug: `git undo` on a reset --hard HEAD^^^ actually doesn't do the right thing so that sucks

usability:

performance:
- [ ] tests are really slow :(
- [ ] it slows down commits LOT  (~60ms with no hooks -> -> 450ms). Rebases are painfully slow.

"portability" issues:
- [ ] possibly use GIT_DIR environment variable to get git dir when in a hook for better accuracy
- [ ] bug: `.git/hooks` might not be accurate to get hooks dir, use libgit2 instead
- [ ] bug: it overwrites all your git hooks

possible problems
- [ ] the thing where index / workdir are commits is a little weird (idea: look at jj's internals)
- [ ] pygit2 dependency is problematic


