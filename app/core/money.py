"""Деньги проекта (docs/02 «Правила денег в ядре»).

Money это Decimal с двумя знаками и фиксированным округлением ROUND_HALF_UP.
В БД сумма хранится целыми копейками (Integer), граница конвертации одна:
репозиторий записывает int(money * 100), читает Money.from_cents(amount_cents).
Двоичное значение с плавающей точкой в конструктор не проходит: его представление
не даёт точной копейки, поэтому принимаются только Decimal, int и str.
"""

from decimal import ROUND_HALF_UP, Decimal

_TWO_PLACES = Decimal("0.01")
_CENTS = Decimal("100")
_ALLOWED = (Decimal, int, str)


class Money:
    """Неизменяемая сумма с двумя знаками; арифметика только в Decimal."""

    __slots__ = ("_amount",)

    def __init__(self, value: Decimal | int | str) -> None:
        if not isinstance(value, _ALLOWED):
            raise TypeError("Money принимает Decimal, int или str")
        self._amount = Decimal(value).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    @property
    def amount(self) -> Decimal:
        """Сумма как Decimal с двумя знаками: значение для API."""
        return self._amount

    @classmethod
    def from_cents(cls, cents: int) -> "Money":
        """Чтение из БД: Money.from_cents(amount_cents)."""
        if not isinstance(cents, int) or isinstance(cents, bool):
            raise TypeError("Копейки это int")
        return cls(Decimal(cents) / _CENTS)

    def to_cents(self) -> int:
        """Запись в БД: amount_cents = int(money * 100); два знака дают точное целое."""
        return int(self._amount * _CENTS)

    def __add__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self._amount + other._amount)

    def __sub__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self._amount - other._amount)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Money):
            return self._amount == other._amount
        # Строки в сравнении не участвуют: Decimal("abc") бросает InvalidOperation,
        # а hash(Decimal) не совпадает с hash(str) - иначе ломается контракт eq/hash
        # для смешанных dict и set (docs/02 §Правила денег).
        if isinstance(other, (Decimal, int)):
            return self._amount == Decimal(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._amount)

    def __repr__(self) -> str:
        return f"Money({self._amount})"

    def __str__(self) -> str:
        return str(self._amount)
