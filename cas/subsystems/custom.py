from cas.common.models import BuildResult, BuildSubsystem


class CustomSubsystem(BuildSubsystem):
    """
    Subsystem that invokes a custom program on build and clean steps.
    """

    def build(self) -> BuildResult:
        args = self.config.get("build")
        return True if not args else self.env.run_tool(args, cwd=self.config.cwd) == 0

    def clean(self) -> bool:
        args = self.config.get("clean")
        return True if not args else self.env.run_tool(args, cwd=self.config.cwd) == 0


_subsystem = CustomSubsystem
