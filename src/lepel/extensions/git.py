import os
import shutil
from pathlib import Path

import git


def save_git_status(output_dir: Path):
    """Save the current Git repository status and modified files to a directory.

    This function inspects the Git repository associated with the current
    working directory (or its parents), records repository metadata (branch
    and commit hash), and identifies files that have staged or unstaged
    changes. Git metadata is written into a ``git/`` subdirectory under the
    provided directory, and copies of the changed files are stored under a
    ``git/changes/`` subdirectory, preserving their relative paths.

    Parameters
    ----------
    output_dir : pathlib.Path
        Target directory in which to store Git metadata and copies of changed files.

    Raises
    ------
    OSError
        If filesystem operations fail.
    """
    try:
        repo = git.Repo(search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        return

    unstaged = [item.a_path for item in repo.index.diff(None)]
    staged = [item.a_path for item in repo.index.diff('Head')]

    changes = [
        changed_file
        for changed_file in unstaged + staged
        if changed_file is not None
        and changed_file not in repo.untracked_files
        and os.path.exists(os.path.join(repo.working_dir, changed_file))
    ]
    changes = sorted(set(changes))

    git_dir = output_dir / 'git'
    git_dir.mkdir(parents=True, exist_ok=True)

    if repo.head.is_detached:
        branch_name = 'detached'
    else:
        branch_name = repo.active_branch.name

    commit_hash = repo.head.object.hexsha

    # Create branch and commit marker files
    (git_dir / f'branch.{branch_name}').touch()
    (git_dir / f'commit.{commit_hash}').touch()

    # Write changed files list
    with open(git_dir / 'changes.txt', 'w') as handle:
        handle.write('\n'.join(changes))

    changes_dir = git_dir / 'changes'
    changes_dir.mkdir(parents=True, exist_ok=True)

    for change in changes:
        source_path = os.path.join(repo.working_dir, change)
        destination_path = changes_dir / change
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source_path, destination_path)
