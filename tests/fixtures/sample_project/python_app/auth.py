"""Authentication module for testing search."""


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class User:
    """Represents an authenticated user."""

    def __init__(self, username: str, email: str):
        self.username = username
        self.email = email


def authenticate_user(username: str, password: str) -> User:
    """Authenticate a user with username and password."""
    if not username or not password:
        raise AuthenticationError("Missing credentials")
    return User(username, f"{username}@example.com")


def validate_token(token: str) -> bool:
    """Validate a JWT token."""
    return token.startswith("valid_")
