"""Setup script for the jvspatial package."""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

# Read version from version.py without importing the package
# This avoids dependency issues during setup
import re
from pathlib import Path


def get_version():
    """Read version from jvspatial/version.py without importing the package."""
    version_file = Path(__file__).parent / "jvspatial" / "version.py"
    with open(version_file, "r") as f:
        content = f.read()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
        else:
            raise ValueError("Could not find __version__ in jvspatial/version.py")


__version__ = get_version()

setup(
    name="jvspatial",
    version=__version__,
    description="An asynchronous object-spatial Python library for persistence and business logic application layers.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="TrueSelph Inc.",
    author_email="adminh@trueselph.com",
    url="https://github.com/trueselph/jvspatial",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "pydantic>=2.0",
        "fastapi",
        "uvicorn",
        "python-multipart",
        "motor",
        "pymongo",
        "aiosqlite>=0.19.0",  # SQLite database backend
        "PyJWT",  # JWT token handling for authentication
        "bcrypt",  # Password hashing for authentication
        "schedule>=1.2.2",  # Job scheduling
        "typing-extensions",  # For @override decorator and enhanced typing
        "boto3",  # AWS SDK for S3 storage support
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21.0",
            "httpx>=0.24.0",
            "pre-commit>=3.0.0",
            "black",  # Code formatter
            "isort",  # Import sorting
            "flake8",  # Linting
            "mypy",  # Type checking
            "pytest-cov",  # Coverage reporting
            "python-dotenv>=1.0.0",  # Environment variable management
        ],
        "test": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21.0",
            "httpx>=0.24.0",
            "pytest-cov",  # Coverage reporting
            "python-dotenv>=1.0.0",  # Environment variable management
        ],
        "scheduler": [
            "schedule>=1.2.2",  # Job scheduling
            "psutil>=5.9.0",  # System monitoring
            "python-dotenv>=1.0.0",  # Environment variable management
        ],
        "cache": [
            "redis[hiredis]>=5.0.0",  # Redis client with C parser for performance
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
)
