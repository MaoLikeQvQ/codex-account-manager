"""API-equivalent estimates from local usage, never subscription balances."""
import math
from datetime import datetime, timedelta

from maox.usage.summary import PRICE_SOURCE, summarize_range
from maox.usage.pricing import get_api_prices


def estimate_quota_amounts(manager, name, limits, now=None):
    result = {'currency': 'USD', 'price_source': PRICE_SOURCE, 'windows': {}}
    if not limits:
        return result
    store = manager._load_store()
    accounts = store.get('accounts', {})
    official = [key for key, value in accounts.items() if manager._account_type(value) == 'official']
    if store.get('active_account') != name or official != [name]:
        result['reason'] = '本机记录不能区分多个官方账号；仅支持唯一且当前启用的官方账号。'
        return result
    buckets = limits.get('rateLimitsByLimitId')
    snapshots = list(buckets.items()) if buckets else [('Codex', limits.get('rateLimits') or {})]
    if len(snapshots) != 1 or snapshots[0][0].lower() != 'codex':
        result['reason'] = '本机用量无法对应这些独立额度分组。'
        return result
    now = now or datetime.now().astimezone()
    prices, result['pricing'] = get_api_prices(manager.paths.app_home)
    result['price_source'] = result['pricing'].get('source', result['price_source'])
    bucket, snapshot = snapshots[0]
    for key in ('primary', 'secondary'):
        window = snapshot.get(key) or {}
        entry = result['windows'][f'{bucket}:{key}'] = {}
        used = window.get('usedPercent')
        duration = window.get('windowDurationMins')
        reset = window.get('resetsAt')
        if (not isinstance(used, (int, float)) or isinstance(used, bool)
                or not math.isfinite(used) or not 0 < used <= 100):
            entry['reason'] = '已用比例为 0 或未知，暂时无法反推周期金额。'
            continue
        if (not isinstance(duration, (int, float)) or isinstance(duration, bool)
                or duration not in (300, 10080)
                or not isinstance(reset, (int, float)) or isinstance(reset, bool)
                or not math.isfinite(reset)):
            entry['reason'] = '缺少可用的周期或重置时间。'
            continue
        try:
            end = datetime.fromtimestamp(reset, now.tzinfo)
            start = end - timedelta(minutes=duration)
            if not start <= now < end:
                entry['reason'] = '额度周期已过期，请刷新。'
                continue
            sample = summarize_range(manager.paths.codex_home, 'openai', False, start, now, api_prices=prices)
        except (OSError, ValueError, OverflowError):
            entry['reason'] = '无法读取本机周期用量。'
            continue
        totals = sample['totals']
        cost = totals['estimated_cost']
        if sample['skipped_files']:
            entry['reason'] = f"{sample['skipped_files']} 个本机记录文件读取失败，暂不估算。"
            continue
        if totals['unpriced_tokens']:
            models = '、'.join(row['model'] for row in sample['models'] if row['unpriced_tokens'])
            entry['reason'] = f'模型缺少价格：{models}，暂不估算。'
            continue
        if not math.isfinite(cost) or cost <= 0:
            entry['reason'] = '本机没有可定价的当前周期 Token 记录。'
            continue
        total = cost * 100 / used
        entry.update(sample_usd=cost, total_usd=total, remaining_usd=total-cost,
                     used_percent=used, sample_start=start.isoformat(), sample_end=now.isoformat())
        if used < 5:
            entry['note'] = '样本较少，百分比取整会放大估算误差。'
    return result
