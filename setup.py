"""
gm-quant: 掘金量化六策略行业差异化融合框架

基于掘金量化 SDK 的 A 股多策略融合交易系统。
覆盖 6 个策略、12 个行业、96 只股票。

安装:
    pip install gm -U        # 掘金 SDK (必需)
    git clone https://github.com/ATboy-web/gm-quant.git
    cd gm-quant
    python offline_backtest.py
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gm-quant",
    version="29.4.0",
    author="ATboy-web",
    description="Six-Strategy Sector-Differentiated Quantitative Trading Framework for A-Shares",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ATboy-web/gm-quant",
    project_urls={
        "Bug Tracker": "https://github.com/ATboy-web/gm-quant/issues",
        "Documentation": "https://github.com/ATboy-web/gm-quant#readme",
        "Source Code": "https://github.com/ATboy-web/gm-quant",
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.13",
        "Operating System :: Microsoft :: Windows",
    ],
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.21",
        "pandas>=1.3",
        "matplotlib>=3.5",
    ],
    extras_require={
        "gm": ["gm>=3.0.183"],    # 掘金量化SDK (需单独安装)
        "dev": ["pytest", "flake8"],
    },
    py_modules=[
        "config",
        "indicators",
        "stock_pool",
        "screener",
        "sentiment_engine",
        "ai_assistant",
        "strategy_mr",
        "strategy_momentum",
        "strategy_vp",
        "strategy_breakout",
        "strategy_dividend",
        "strategy_reversal",
        "strategy_factory",
        "sector_config",
        "fusion",
        "executor",
        "main",
        "offline_backtest",
        "visualizer",
        "gm_logger",
        "trace",
    ],
)
