from setuptools import find_packages, setup

with open("README.md", "rt", encoding="UTF-8") as fh:
    long_description = fh.read()

dependencies = [
    "chia-blockchain==2.4.4",
]

dev_dependencies = [
    "pylint==3.3.1",
    "pytest==8.3.3",
    "pytest-asyncio==0.24.0",
    "pytest-monitor==1.6.6; sys_platform == 'linux'",
    "pytest-xdist==3.6.1",
    "isort==5.13.2",
    "faker==30.8.0",
    "flake8==7.1.1",
    "mypy==1.12.0",
    "black==24.10.0",
    "types-setuptools==75.1.0.20241014",
    "pre-commit==3.5.0; python_version < '3.9'",
    "pre-commit==4.0.1; python_version >= '3.9'",
]

setup(
    name="chianft",
    version="0.1",
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
    license="https://opensource.org/licenses/Apache-2.0",
    description="Chia NFT minting toolkit",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
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
