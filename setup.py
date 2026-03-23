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
        "fastapi>=0.100.0",
        "uvicorn>=0.23.0",
        "python-multipart>=0.0.6",
        "motor>=3.0.0",
        "pymongo>=4.0.0",
        "aiosqlite>=0.19.0",  # SQLite database backend
        "PyJWT>=2.0.0",  # JWT token handling for authentication
        "bcrypt>=4.0.0",  # Password hashing for authentication
        "email-validator>=2.0.0",  # Email validation for Pydantic EmailStr
        "schedule>=1.2.2",  # Job scheduling
        "typing-extensions>=4.0.0",  # For @override decorator and enhanced typing
        "aiofiles>=23.0.0",  # Async file operations for JsonDB
    ],
    extras_require={
        "lambda": [
            "aioboto3>=15.5.0",
            "boto3>=1.28.0",
        ],
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
