import setuptools

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="cas",
    version="1.0.5",
    description="Chaos Automation System",
    url="https://github.com/ChaosInitiative/CAS",
    author="Chaos Initiative",
    author_email="contact@chaosinitiative.com",
    license="mit",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(include=["cas", "cas.*"]),
    package_data={"cas": ["schemas"]},
    entry_points={"console_scripts": ["casbuild = cas.cli:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[
        "jsonschema",
        "simpleeval",
        "appdirs",
        "dotmap",
        "tqdm",
        "vdf",
        "requests",
    ],
    dependency_links=["https://github.com/TeamSpen210/srctools#egg=srctools"],
)
