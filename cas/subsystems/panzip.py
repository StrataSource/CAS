from cas.common.models import BuildResult, BuildSubsystem


class PanZipSubsystem(BuildSubsystem):
    def build(self, force: bool = False) -> BuildResult:
        return BuildResult(True)

    def clean(self) -> bool:
        return True


_subsystem = PanZipSubsystem
