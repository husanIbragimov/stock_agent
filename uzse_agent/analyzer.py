"""Narx trendi + yangiliklar sentimentini birlashtirib, oddiy 'signal' chiqaradi.

DIQQAT: Bu yerdagi signal moliyaviy maslahat EMAS. U faqat tarixiy narx
harakati va yangiliklar tonini yig'ib, o'qish uchun qulay qisqa xulosa
beradi. Real bozor xatti-harakatini hech qanday agent 100% aniqlikda
bashorat qila olmaydi — bu haqda README'da ham alohida ogohlantirilgan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


@dataclass
class AnalysisResult:
    ticker: str
    current_price: float | None
    pct_change_recent: float | None  # saqlangan tarixdagi birinchi va oxirgi narx orasidagi %
    news_avg_sentiment: float | None
    news_count: int
    signal: str
    reasons: list[str] = field(default_factory=list)


def _pct_change(history: list[tuple[str, float]]) -> float | None:
    if len(history) < 2:
        return None
    first_price = history[0][1]
    last_price = history[-1][1]
    if first_price == 0:
        return None
    return round((last_price - first_price) / first_price * 100, 2)


def analyze(
    ticker: str,
    current_price: float | None,
    history: list[tuple[str, float]],
    news_sentiments: list[float],
) -> AnalysisResult:
    pct_change = _pct_change(history)
    avg_sentiment = round(mean(news_sentiments), 3) if news_sentiments else None
    news_count = len(news_sentiments)

    reasons: list[str] = []
    score = 0.0

    if pct_change is not None:
        if pct_change >= 5:
            score += 1
            reasons.append(f"Narx so'nggi kuzatuv davrida +{pct_change}% o'sgan")
        elif pct_change <= -5:
            score -= 1
            reasons.append(f"Narx so'nggi kuzatuv davrida {pct_change}% pasaygan")
        else:
            reasons.append(f"Narx nisbatan barqaror ({pct_change:+.2f}%)")

    if avg_sentiment is not None:
        if avg_sentiment > 0.15:
            score += 1
            reasons.append(f"So'nggi {news_count} ta yangilik umuman ijobiy ohangda")
        elif avg_sentiment < -0.15:
            score -= 1
            reasons.append(f"So'nggi {news_count} ta yangilik umuman salbiy ohangda")
        else:
            reasons.append(f"So'nggi {news_count} ta yangilik neytral/aralash")
    else:
        reasons.append("Tegishli yangilik topilmadi")

    if score >= 1.5:
        signal = "Ijobiy trend"
    elif score <= -1.5:
        signal = "Salbiy trend — ehtiyot bo'ling"
    elif score > 0:
        signal = "Yengil ijobiy"
    elif score < 0:
        signal = "Yengil salbiy"
    else:
        signal = "Neytral"

    return AnalysisResult(
        ticker=ticker,
        current_price=current_price,
        pct_change_recent=pct_change,
        news_avg_sentiment=avg_sentiment,
        news_count=news_count,
        signal=signal,
        reasons=reasons,
    )
