from __future__ import annotations

from setuptools import find_packages, setup

with open("README.md", encoding="UTF-8") as fh:
    long_description = fh.read()

dependencies = [
    "chia-blockchain==2.5.4",
]

dev_dependencies = [
    "pytest==8.4.0",
    "pytest-asyncio==1.0.0",
    "pytest-monitor==1.6.6; sys_platform == 'linux'",
    "pytest-xdist==3.7.0",
    "ruff>=0.8.1",
    "faker==37.4.0",
    "mypy==1.16.1",
    "types-setuptools==80.9.0.20250529",
    "pre-commit==4.2.0; python_version >= '3.9'",
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
