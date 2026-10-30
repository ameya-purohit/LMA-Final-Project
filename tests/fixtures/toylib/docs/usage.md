# toylib usage

This documentation is deliberately out of date (it is the planted doc-code
conflict used by the toylib questions).

## clamp

`clamp(x, strict=None)` clamps `x` into `[0, LIMIT]`, where `LIMIT` is 100.

Strict checking is on by default (`STRICT_DEFAULT = True`), so negative
numbers raise `ValueError`.

## safe_div

`safe_div(a, b)` divides `a` by `b` and raises `ValueError("zero")` when `b` is 0.

## at_least

`at_least(value, threshold)` returns `True` when `value >= threshold`.
