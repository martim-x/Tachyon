"""Порт экспорта отчётов и его контракт (docs/02 §export).

export - это порт и набор адаптеров одного интерфейса: xlsx, pdf и csv -
три реализации одного контракта, ни один домен не знает про библиотеки
файлов. Сборка адаптера происходит снаружи, в app.interface.api.deps.

Сигнатура порта адаптирована под HTTP-ответ (docs/03 §S7.1): вместо записи
в файл на диске адаптер отдаёт готовый байтовый поток с именем и MIME-типом,
чтобы роутер собрал Content-Disposition без внедоменного ввода-вывода.
"""

from dataclasses import dataclass
from typing import Protocol

from app.domains.reporting.schemas import ExportReportDTO


@dataclass(frozen=True, slots=True)
class ExportFile:
    """Готовый файл экспорта: имя, MIME-тип и содержимое."""

    filename: str
    media_type: str
    content: bytes


class ReportExporter(Protocol):
    """Порт «отчёт -> файл»: формат вывода, а не бизнес-правило."""

    def export(self, report: ExportReportDTO) -> ExportFile: ...
