from setuptools import setup

setup(
    name="neuro",
    version="1.0",
    packages=[
        "neuro.core",
        "neuro.core.data",
        "neuro.core.files",
        "neuro.tools.api",
        "neuro.tools.terminal",
        "neuro.tools.terminal.commands",
        "neuro.utils"],
    include_package_data=True,
    entry_points="""
        [console_scripts]
        neuro=neuro.tools.terminal.cli:cli
    """
)
