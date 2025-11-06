"""Setup configuration for affinetes package"""

from setuptools import setup, find_packages
from pathlib import Path

# Read version from __version__.py
version = {}
version_file = Path(__file__).parent / "affinetes" / "__version__.py"
with open(version_file) as f:
    exec(f.read(), version)

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
with open(readme_file, encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="affinetes",
    version=version["__version__"],
    description="Container-based Environment Management System",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Affinetes Team",
    author_email="contact@affinetes.io",
    url="https://github.com/affinetes/affinetes",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        "docker>=6.0.0",
        "aiohttp>=3.8.0",
        "tabulate>=0.9.0",
        "pyyaml>=6.0",
        "nest-asyncio>=1.5.0",
        "httpx>=0.24.0",
        "paramiko>=3.0.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "afs=affinetes.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Systems Administration",
    ],
)