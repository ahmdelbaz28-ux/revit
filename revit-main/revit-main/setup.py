"""
Setup script for FireAI Agent Communication Protocol (FACP)
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("VERSION", "r", encoding="utf-8") as vh:
    version = vh.read().strip()

setup(
    name="facp",
    version=version,
    author="FireAI Team",
    author_email="info@fireai.example.com",
    description="FireAI Agent Communication Protocol - A secure, deterministic communication protocol for engineering AI agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/fireai/facp",
    packages=find_packages(where="facp"),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Communications",
        "Topic :: Security"
    ],
    python_requires='>=3.12',
    install_requires=[
        "psutil>=5.8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
        ],
        "web": [
            "fastapi>=0.68.0",
            "uvicorn>=0.15.0",
        ],
        "ws": [
            "websockets>=10.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "facp-server=facp.__main__:main",
        ],
    },
    include_package_data=True,
    zip_safe=False
)