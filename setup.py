from setuptools import find_packages, setup

with open("README.md", "rt", encoding="UTF-8") as fh:
    long_description = fh.read()

dependencies = [
    "chia-blockchain==2.1.4",
]

dev_dependencies = [
    "pre-commit==3.6.1",
    "pylint==3.0.3",
    "pytest==7.4.4",
    "pytest-asyncio==0.23.5",
    "pytest-monitor==1.6.6; sys_platform == 'linux'",
    "pytest-xdist==3.5.0",
    "isort==5.13.2",
    "faker==23.1.0",
    "flake8==7.0.0",
    "mypy==1.8.0",
    "black==24.1.1",
    "types-setuptools==69.0.0.20240125",
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
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
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
