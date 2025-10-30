"""Setup script for affinetes"""

from setuptools import setup, find_packages
from pathlib import Path

# Read version
version_file = Path(__file__).parent / "affinetes" / "__version__.py"
version = {}
exec(version_file.read_text(), version)

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="affinetes",
    version=version["__version__"],
    description="Container-based environment execution framework with HTTP",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Affinetes Team",
    python_requires=">=3.8",
    packages=find_packages(exclude=["test", "test.*", "environments", "environments.*", "docs", "docs.*"]),
    install_requires=[
        "pyyaml>=6.0",
        "python-dotenv>=1.0.0",
        "docker>=7.0.0",
        "httpx>=0.27.0",
        "paramiko>=3.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "affinetes=affinetes.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)