"""
Crypto quant platform MVP bootstrap script.

This script focuses on two things:
1) Quickly wiring MainEngine with a crypto gateway package.
2) Providing a repeatable startup path for UI/no-UI mode.
"""

from __future__ import annotations

import argparse
import inspect
from importlib import import_module
from typing import Any

from vnpy.event import EventEngine
from vnpy.trader.app import BaseApp
from vnpy.trader.engine import MainEngine
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.ui import MainWindow, create_qapp


def parse_args() -> argparse.Namespace:
    """Parse startup arguments."""
    parser = argparse.ArgumentParser(description="Crypto MVP starter for VeighNa")
    parser.add_argument(
        "--mode",
        choices=["ui", "no_ui"],
        default="no_ui",
        help="Startup mode.",
    )
    parser.add_argument(
        "--gateway-module",
        default="vnpy_binance",
        help="Gateway python module, e.g. vnpy_binance/vnpy_okx/vnpy_bybit.",
    )
    parser.add_argument(
        "--gateway-class",
        default="",
        help="Gateway class name. If empty, auto-discover from module.",
    )
    parser.add_argument(
        "--apps",
        default="",
        help=(
            "Optional app list in format "
            "'module_a:ClassA,module_b:ClassB'. "
            "Example: 'vnpy_ctastrategy:CtaStrategyApp,vnpy_riskmanager:RiskManagerApp'"
        ),
    )
    return parser.parse_args()


def import_module_or_raise(module_name: str) -> Any:
    """Import module and give actionable error message on failure."""
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"无法导入模块 {module_name}。"
            f"请先安装对应包，例如：pip install {module_name}"
        ) from exc


def load_gateway_class(module_name: str, class_name: str) -> type[BaseGateway]:
    """Load gateway class by explicit class name or auto-discovery."""
    module: Any = import_module_or_raise(module_name)

    if class_name:
        gateway_class: Any | None = getattr(module, class_name, None)
        if not gateway_class:
            raise RuntimeError(f"模块 {module_name} 中不存在类 {class_name}")
        if not inspect.isclass(gateway_class) or not issubclass(gateway_class, BaseGateway):
            raise RuntimeError(f"{module_name}:{class_name} 不是 BaseGateway 子类")
        return gateway_class

    candidates: list[type[BaseGateway]] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj is BaseGateway:
            continue
        if issubclass(obj, BaseGateway) and obj.__module__.startswith(module_name):
            candidates.append(obj)

    if len(candidates) == 1:
        return candidates[0]

    names: list[str] = [c.__name__ for c in candidates]
    raise RuntimeError(
        "自动识别网关类失败。"
        f"模块 {module_name} 发现候选类: {names or '[]'}。"
        "请使用 --gateway-class 显式指定。"
    )


def load_app_classes(spec: str) -> list[type[BaseApp]]:
    """Load optional app classes from module:class list."""
    app_classes: list[type[BaseApp]] = []
    if not spec:
        return app_classes

    raw_items: list[str] = [item.strip() for item in spec.split(",") if item.strip()]
    for item in raw_items:
        if ":" not in item:
            raise RuntimeError(f"应用格式错误: {item}，应为 module:Class")

        module_name, class_name = item.split(":", maxsplit=1)
        module: Any = import_module_or_raise(module_name)
        app_class: Any | None = getattr(module, class_name, None)
        if not app_class:
            raise RuntimeError(f"模块 {module_name} 中不存在类 {class_name}")
        if not inspect.isclass(app_class) or not issubclass(app_class, BaseApp):
            raise RuntimeError(f"{module_name}:{class_name} 不是 BaseApp 子类")

        app_classes.append(app_class)

    return app_classes


def bootstrap_engine(
    gateway_module: str,
    gateway_class_name: str,
    apps: str,
) -> tuple[MainEngine, EventEngine]:
    """Build MainEngine and load gateway/apps."""
    gateway_class: type[BaseGateway] = load_gateway_class(gateway_module, gateway_class_name)
    app_classes: list[type[BaseApp]] = load_app_classes(apps)

    event_engine: EventEngine = EventEngine()
    main_engine: MainEngine = MainEngine(event_engine)

    main_engine.add_gateway(gateway_class)
    for app_class in app_classes:
        main_engine.add_app(app_class)

    print(f"[OK] 已加载网关: {gateway_class.__name__}")
    print(f"[OK] 已加载应用: {[cls.__name__ for cls in app_classes]}")
    print("[NEXT] 请在UI中连接网关，或在脚本中调用 main_engine.connect(setting, gateway_name)")
    return main_engine, event_engine


def run_ui(gateway_module: str, gateway_class_name: str, apps: str) -> None:
    """Run with VeighNa Trader GUI."""
    qapp = create_qapp()
    main_engine, event_engine = bootstrap_engine(gateway_module, gateway_class_name, apps)
    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()
    qapp.exec()


def run_no_ui(gateway_module: str, gateway_class_name: str, apps: str) -> None:
    """Run in no-UI mode and print startup status."""
    bootstrap_engine(gateway_module, gateway_class_name, apps)


def main() -> None:
    """Program entry."""
    args = parse_args()
    if args.mode == "ui":
        run_ui(args.gateway_module, args.gateway_class, args.apps)
    else:
        run_no_ui(args.gateway_module, args.gateway_class, args.apps)


if __name__ == "__main__":
    main()
