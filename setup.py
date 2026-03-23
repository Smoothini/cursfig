from setuptools import setup, find_packages

setup(
    name="cursfig",
    version="0.1.0",
    description="Configuration backup and restore tool",
    packages=find_packages(),
    package_data={"cursfig": ["data/*.yaml"]},
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "pyyaml>=6.0",
        "click>=8.1",
        "rich>=13.0",
        "textual>=0.50",
    ],
    extras_require={
        "github": ["PyGithub>=2.0"],
        "gdrive": [
            "google-api-python-client>=2.0",
            "google-auth-oauthlib>=1.0",
        ],
        "all": [
            "PyGithub>=2.0",
            "google-api-python-client>=2.0",
            "google-auth-oauthlib>=1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "cursfig=cursfig.cli:main",
        ],
    },
)
