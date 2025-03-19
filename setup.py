from __future__ import annotations

from setuptools import find_packages, setup

with open("README.md", encoding="UTF-8") as fh:
    long_description = fh.read()

dependencies = [
    "chia-blockchain==2.5.2",
]

dev_dependencies = [
    "pytest==8.3.5",
    "pytest-asyncio==0.25.3",
    "pytest-monitor==1.6.6; sys_platform == 'linux'",
    "pytest-xdist==3.6.1",
    "ruff>=0.8.1",
    "faker==37.0.0",
    "mypy==1.15.0",
    "types-setuptools==76.0.0.20250313",
    "pre-commit==4.1.0; python_version >= '3.9'",
]

setup(
    name="chianft",
    packages=find_packages(exclude=("tests",)),
    author="Geoff Walmsley",
    entry_points={
        "console_scripts": ["chianft = chianft.cmds.cli:main"],
    },
    package_data={
        "": ["*.clvm", "*.clvm.hex", "*.clib", "*.clsp", "*.clsp.hex"],
    },
    author_email="g.walmsley@chia.net",
    setup_requires=["setuptools_scm"],
    install_requires=dependencies,
    url="https://github.com/Chia-Network",
    license="Apache-2.0",
    description="Chia NFT minting toolkit",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Security :: Cryptography",
    ],
    extras_require=dict(
        dev=dev_dependencies,
    ),
    project_urls={
        "Bug Reports": "https://github.com/Chia-Network/chia-nft-minting-tool",
        "Source": "https://github.com/Chia-Network/chia-nft-minting-tool",
    },
)
