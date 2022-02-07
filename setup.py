from setuptools import setup

setup(
    name="neuro",
    version="1.1.1",
    packages=[
        "neuro.core",
        "neuro.core.data",
        "neuro.core.files",
        "neuro.tools.api",
        "neuro.tools.local",
        "neuro.tools.terminal",
        "neuro.tools.terminal.commands",
        "neuro.tools.wrappers",
        "neuro.utils"],
    include_package_data=True,
    entry_points="""
        [console_scripts]
        neuro=neuro.tools.terminal.cli:cli
    """
)
