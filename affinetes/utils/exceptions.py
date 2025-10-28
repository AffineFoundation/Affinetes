"""Custom exceptions for affinetes"""


class RayfineEnvError(Exception):
    """Base exception for all affinetes errors"""
    pass


class ValidationError(RayfineEnvError):
    """Input validation failed"""
    pass


class ImageBuildError(RayfineEnvError):
    """Image build/push/pull failed"""
    pass


class ImageNotFoundError(RayfineEnvError):
    """Docker image not found"""
    pass


class ContainerError(RayfineEnvError):
    """Docker container operation failed"""
    pass


class RayConnectionError(RayfineEnvError):
    """Ray cluster connection failed"""
    pass


class RayExecutionError(RayfineEnvError):
    """Ray Actor method execution failed"""
    pass


class ExecutionError(RayfineEnvError):
    """Remote execution failed"""
    pass


class BackendError(RayfineEnvError):
    """Backend operation failed"""
    pass


class SetupError(RayfineEnvError):
    """Environment setup failed"""
    pass


class EnvironmentError(RayfineEnvError):
    """Environment operation failed"""
    pass


class NotImplementedError(RayfineEnvError):
    """Feature not yet implemented"""
    pass