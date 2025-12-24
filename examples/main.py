from lepel import DependencyManager, PipelineStep, run_pipeline
from lepel.cli import cli_args_to_config, default_argparser


class FooStep(PipelineStep):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def run(self, foo: int) -> None:
        print(self.name, 'foo:', foo)


def main(dependencies: DependencyManager) -> None:
    dependencies.update_context_variables(foo=42)
    FooStep('Foo')


if __name__ == '__main__':
    argparser = default_argparser()
    namespace, rest_args = argparser.parse_known_args()

    run_pipeline(
        main,
        output_dir=namespace.output_dir,
        config_file=namespace.config,
        checkpoint=namespace.checkpoint,
        **cli_args_to_config(rest_args)
    )
