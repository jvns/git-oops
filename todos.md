problems:

- [X] index commit in snapshot is not actually immutable, that sucks (fixed)
- [X] can't do snapshots in reference-transaction or post-index-change (fix: don't run hooks)
- [X] fix snapshots inside snapshots (fix: don't run a hooks, do I still need the lockfile?)
- [X] messages don't give you the actual operation that's running
- [X] 130ms to make a recording is a bit slow (idea: pygit2?? -- for now)
- [X] lock file management feels kinda flaky
- [X] fix "ref HEAD is not a symbolic ref" during rebase
- [ ] pygit2 dependency is problematic
- [ ] need to implement restore
- [ ] tests are really slow :(
- [ ] don't include message in snapshot state (to make equality checking more accurate)
- [ ] commit is like 4 operations, reset is 3 operations (idea: implement a wrapper?)

possible problems
- [ ] the thing where index / workdir are commits is a little weird (idea: look at jj's internals)

