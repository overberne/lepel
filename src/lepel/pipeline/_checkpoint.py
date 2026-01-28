from lepel.core import RecipeStep


class Checkpoint(RecipeStep):
    def __init__(self, name: str) -> None:
        """Create a pipeline checkpoint step.

        The checkpoint step, when reached during pipeline execution, serializes
        the current dependency manager state into a :class:`~lepel.checkpoint.Checkpoint`
        and saves it to the pipeline's ``checkpoints`` directory.

        Parameters
        ----------
        name : str
            Logical name for the checkpoint. Checkpoints saved by this step are
            written to the output ``checkpoints`` directory with this name as
            the filename. The name can later be provided to ``run_recipe``
            via the ``checkpoint`` argument to resume execution from that
            checkpoint.
        """
        super().__init__()
        self.name = name

    def run(self) -> None:
        pass
