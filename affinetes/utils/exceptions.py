"""Custom exceptions for affinetes"""


class AffinetesError(Exception):
    """Base exception for all affinetes errors"""
    pass


class ValidationError(AffinetesError):
    """Input validation failed"""
    pass


class ImageBuildError(AffinetesError):
    """Image build/push/pull failed"""
    pass


class ImageNotFoundError(AffinetesError):
    """Docker image not found"""
    pass


class ContainerError(AffinetesError):
    """Docker container operation failed"""
    pass


class ExecutionError(AffinetesError):
    """Remote execution failed"""
    pass


class BackendError(AffinetesError):
    """Backend operation failed"""
    pass


class SetupError(AffinetesError):
    """Environment setup failed"""
    pass


class EnvironmentError(AffinetesError):
    """Environment operation failed"""
    pass


class NotImplementedError(AffinetesError):
    """Feature not yet implemented"""
    pass