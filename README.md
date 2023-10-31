**EXPERIMENTAL SOFTWARE, MAY DO DESTRUCTIVE THINGS TO YOUR GIT REPOSITORY. SOME OF THE FEATURES DESCRIBED IN THIS README DO NOT WORK PROPERLY.**

# git oops

Have you ever made a mistake with git and wished you could just type `git undo`
instead of having to remember a weird incantation? With `git oops`, you can!

```
$ git rebase -i main
$ git oops undo
```

## installation

* Put the `git-oops` script into your PATH somewhere
* Install `pygit2` globally on your system
* Run `git oops init` in a repository to install the hooks
* If you'd like, alias `git undo` to `git oops undo`

Now `git-oops` will automatically take a snapshot any time you do anything in
your Git repo.

## basic usage

* `git oops undo` will undo the last operation.
* `git oops history` shows you the history of all snapshots taken using a curses-based interface and lets you interactively pick one to restore.

## advanced usage

* `git oops record` manually records a snapshot. 
* `git oops restore COMMIT_ID` restores a specific snapshot

## how it works

when `git oops record` takes a snapshot, here's what it does:

1. **save your staging area and workdir**: It creates a commit for your current staging area and working directory (very similarly to how `git stash` does).
2. **get HEAD**
3. **get all your branches and tags**
4. **check for uniqueness**: If the snapshot is exactly the same as the previous snapshot, it'll exit
5. **record everything in a commit**. Here's an example commit (from this repository). The metadata is stored in the commit message.
```
FormatVersion: 1
HEAD: refs/heads/main
Index: 20568a3a49feda34ad6aaa3aff7d7a578a8dee0d
Workdir: 4d1a195dc04ab74cfe1cd94da826ce5b0069d264
Refs:
refs/heads/libgit2: c02fc253375108ec797b6af3ca957e8ea0cc36b9
refs/heads/main: 1b4cdfab2900b3b99473560e76e3f91c560364a0
refs/heads/test: 9ac4a5d8e10b04cdddab698e8a9053e7e645543c
refs/heads/test2: 4247707e426f4b890ecd7314376c4d706a2d799d
```
6. **update the git-undo reference**: It updates `refs/git-undo` to point at the commit it created in step 5.
7. **update the reflog**: it updates the reflog for `refs/git-undo` to include the new commit

More details about other commands:

* `git oops history` retrieves the history from the reflog for `refs/git-undo`
* `git oops restore COMMIT_ID`:
  * retrieves COMMIT_ID 
  * runs `git -c core.hooksPath=/dev/null restore --source WORKDIR_COMMIT`
  * runs `git -c core.hooksPath=/dev/null restore --staged --source INDEX_COMMIT`
  * updates all the branches and tags from the snapshot. It will not delete any branches or tags, to avoid deleting their reflog.
* `git oops history`:
  * runs the equivalent of `git reflog git-oops` to get a list of histories
  * gives you an interactive UI to choose one to restore
* `git oops undo`:
  * runs the equivalent of `git reflog git-oops` to get a list of histories
  * finds the first one where any of your references changed and restores that one
* `git oops init` installs the following hooks: post-applypatch, post-checkout, pre-commit, post-commit, post-merge, post-rewrite, post-index-change, reference-transaction
  * when the hooks run, it runs `git oops record`


## acknowledgements

People who helped: Kamal Marhubi, Marie Flanagan

Inspired by GitUp, jj, and git-branchless.

