"""結果表示モジュール.

asr / translation の結果メッセージを受け取り出力する `TranslationOutput` と、
その標準実装であるコンソール出力 `ConsoleOutput` を提供する。
"""

from output.base import TranslationOutput
from output.console import ConsoleOutput

__all__ = ["ConsoleOutput", "TranslationOutput"]
