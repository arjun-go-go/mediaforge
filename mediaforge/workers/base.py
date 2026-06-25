from dataclasses import dataclass, field

from mediaforge.models.job import AssetOutput


@dataclass
class WorkerResult:
    success: list[AssetOutput] = field(default_factory=list)
    failed: list[AssetOutput] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return not self.failed
