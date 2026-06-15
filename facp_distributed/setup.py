"""
Setup file for Distributed FACP System
"""
import os

from setuptools import find_packages, setup


def read_version():
    """Read version from VERSION file"""
    version_file = os.path.join(os.path.dirname(__file__), "..", "VERSION")
    try:
        with open(version_file, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return "1.1.0"  # Default version


def read_readme():
    """Read README file"""
    readme_file = os.path.join(os.path.dirname(__file__), "..", "README.md")
    try:
        with open(readme_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "Distributed FireAI Agent Communication Protocol (FACP) System"


setup(
    name="facp-distributed",
    version=read_version(),
    author="FireAI Engineering Team",
    author_email="engineering@fireai.ai",
    description="Distributed FireAI Agent Communication Protocol (FACP) v1.1 System",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/fireai/facp-distributed",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.10",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: System :: Distributed Computing",
        "Topic :: Communications"
    ],
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "pyjwt>=2.8.0",
        "redis>=5.0.0",
        "aiohttp>=3.9.0",
        "websockets>=11.0.0",
        "nats-py>=2.7.0",
        "cryptography>=41.0.0",
        "passlib>=1.7.0",
        "python-multipart>=0.0.6",
        "pydantic>=2.0.0",
        "typing-extensions>=4.0.0",
        "psutil>=5.9.0",
        "prometheus-client>=0.19.0",
        "structlog>=23.0.0",
        "python-json-logger>=2.0.0"
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "isort>=5.0.0",
            "pre-commit>=3.0.0",
        ],
        "docs": [
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.0.0",
            "sphinx-autodoc-typehints>=1.23.0",
        ],
        "monitoring": [
            "prometheus-client>=0.19.0",
            "opentelemetry-api>=1.20.0",
            "opentelemetry-sdk>=1.20.0",
            "opentelemetry-instrumentation-fastapi>=0.41b0",
        ]
    },
    entry_points={
        "console_scripts": [
            "facp-distributed=facp_distributed.__main__:main",
            "facp-cluster-manager=facp_distributed.cluster_manager:main",
            "facp-node=facp_distributed.node_runner:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    project_urls={
        "Bug Reports": "https://github.com/fireai/facp-distributed/issues",
        "Documentation": "https://fireai.github.io/facp-distributed/",
        "Source": "https://github.com/fireai/facp-distributed",
        "Changelog": "https://github.com/fireai/facp-distributed/releases",
    },
)
