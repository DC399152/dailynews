class ToolFailure(RuntimeError):
    """Expected tool failure that can be safely returned to the model."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ToolPolicyViolation(ToolFailure):
    """Raised when a tool request violates a configured safety boundary."""
