# LEarning PipelinE Library (LEPEL)

## Installation

Command: `pip install -e .`


## Pipeline steps

Ensure each step has handles its own random seeds, so that when restoring from a save point the behaviour is deterministic without having to store random seeds, as this is no longer trivial in numpy.

Create pure functions / steps so there are no side-effects which can change results when restoring

Maybe let user pass a save/restore function to the checkpoint function?
- These would create pickle-able dicts
- Stored in a checkpoints subdir of the output
- Then run with --checkpoint to use the latest, or --checkpoint #path-to-file#
- Maybe include a get_state_dict and load_state_dict on certain steps or dependencies?
- It is going to be difficult to restore dependencies to the correct state

- when creating checkpoints
  - either incremental naming
  - or a second function that overwrites the latest one on subsequent calls

- It would be nice to be able to interrupt a long running experiment if you have to say pack up your laptop.
- Call continue pipeline function
  - Called on the copy of the pipeline file
  - looks for checkpoints in relative folder
  - maybe not even a continue function,just make it part of run_pipeline with a flag