"""Fetch public OpenAI model prices with a local daily cache."""
import json
import math
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from urllib.request import Request, urlopen

from maox.usage.summary import API_PRICES, PRICE_SOURCE

PRICING_URL = PRICE_SOURCE + '.md'
CACHE_TTL = 24 * 60 * 60
_CACHE_LOCK = Lock()


def parse_api_prices(markdown):
    marker = '| Model | Short context input |'
    if marker not in markdown:
        raise ValueError('官方价格表格式已变化')
    table = markdown.split(marker, 1)[1].splitlines()[1:]
    prices = {}
    for line in table:
        if not line.startswith('|'):
            break
        cells = [value.strip() for value in line.strip('|').split('|')]
        if cells[0].startswith('---'):
            continue
        if len(cells) != 9:
            raise ValueError('官方价格列不完整')
        model = cells[0].split(' ', 1)[0]
        if not re.fullmatch(r'[a-zA-Z0-9._:-]+', model):
            raise ValueError('官方模型名称格式已变化')
        values = []
        for value in cells[1:]:
            if value == '-':
                values.append(None)
                continue
            number = float(value.removeprefix('$').replace(',', ''))
            if not math.isfinite(number) or number < 0:
                raise ValueError('官方价格数值无效')
            values.append(number)
        short, long = values[:4], values[4:]
        if short[0] is None or short[3] is None:
            raise ValueError('官方输入或输出价格缺失')
        prices[model] = [short, long if long[0] is not None and long[3] is not None else None]
    if not prices:
        raise ValueError('官方价格表为空')
    return prices


MODELS_DEV = 'https://models.dev/api.json'
LITELLM = 'https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json'
OPENROUTER = 'https://openrouter.ai/api/v1/models'


def _rate(value, scale=1):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value) * scale
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _rates(cost, fields, scale=1):
    values = [_rate(cost.get(field), scale) for field in fields]
    return values if values[0] is not None and values[3] is not None else None


def parse_structured_prices(data, source):
    prices = {}
    if source == MODELS_DEV:
        models = data.get('openai', {}).get('models', {})
        entries = ((name, model.get('cost', {})) for name, model in models.items() if isinstance(model, dict))
        fields = ('input', 'cache_read', 'cache_write', 'output')
        for name, cost in entries:
            if not isinstance(cost, dict):
                continue
            base = _rates(cost, fields)
            tiers = cost.get('tiers', [])
            if not isinstance(tiers, list):
                continue
            relevant = [tier for tier in tiers if isinstance(tier, dict) and tier.get('tier', {}).get('type') == 'context']
            if any(tier['tier'].get('size') != 272000 for tier in relevant) or len(relevant) > 1:
                continue
            long = _rates(relevant[0], fields) if relevant else None
            if base and (not relevant or long):
                prices[name] = [base, long]
    elif source == LITELLM:
        fields = ('input_cost_per_token', 'cache_read_input_token_cost', 'cache_creation_input_token_cost', 'output_cost_per_token')
        for name, cost in data.items():
            if not isinstance(cost, dict) or cost.get('litellm_provider') != 'openai' or '/' in name:
                continue
            base = _rates(cost, fields, 1_000_000)
            long = _rates(cost, tuple(field + '_above_272k_tokens' for field in fields), 1_000_000)
            if base:
                prices[name] = [base, long]
    elif source == OPENROUTER:
        fields = ('prompt', 'input_cache_read', 'input_cache_write', 'completion')
        for model in data.get('data', []):
            name = model.get('id', '')
            if not name.startswith('openai/'):
                continue
            cost = model.get('pricing') or {}
            base = _rates(cost, fields, 1_000_000)
            tiers = cost.get('overrides', []) or []
            if len(tiers) > 1 or any(tier.get('min_prompt_tokens') != 272000 for tier in tiers):
                continue
            long = _rates(tiers[0], fields, 1_000_000) if tiers else None
            if base and (not tiers or long):
                prices[name.removeprefix('openai/')] = [base, long]
    if not prices:
        raise ValueError('价格数据为空或格式无效')
    return prices


def get_api_prices(app_home, *, force_refresh=False):
    with _CACHE_LOCK:
        return _get_api_prices(app_home, force_refresh)


def _get_api_prices(app_home, force_refresh):
    cache_path = Path(app_home) / 'api-prices-cache.json'
    now = time.time()
    cached = None
    try:
        cached = json.loads(cache_path.read_text())
        if 'markdown' in cached:
            cached_rates = parse_api_prices(cached['markdown'])
            cached_source = PRICE_SOURCE
        else:
            cached_source = cached['source']
            cached_rates = parse_structured_prices(cached['data'], cached_source)
            if not force_refresh and now - cached['fetched_at'] < CACHE_TTL:
                return cached_rates, {'source': cached_source, 'updated_at': cached['fetched_at'], 'status': 'cached'}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        cached = None
    for source in (MODELS_DEV, LITELLM, OPENROUTER):
        try:
            request = Request(source, headers={'Accept': 'application/json', 'User-Agent': 'MaoX-Account-Manager'})
            with urlopen(request, timeout=8) as response:
                raw = response.read(30_000_001)
                if len(raw) > 30_000_000:
                    raise ValueError('价格数据超过大小限制')
                data = json.loads(raw)
            rates = parse_structured_prices(data, source)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
        metadata = {'source': source, 'updated_at': now, 'status': 'fresh'}
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix='.api-prices-', dir=cache_path.parent) as directory:
                temporary = Path(directory) / cache_path.name
                temporary.write_text(json.dumps({'fetched_at': now, 'source': source, 'data': data}), encoding='utf-8')
                temporary.replace(cache_path)
        except OSError:
            metadata['warning'] = '价格已更新，但本地缓存保存失败。'
        return rates, metadata
    if cached:
        return cached_rates, {'source': cached_source, 'updated_at': cached['fetched_at'], 'status': 'stale',
                              'warning': '价格更新失败，使用上次缓存价格。'}
    return API_PRICES, {'source': PRICE_SOURCE, 'status': 'bundled',
                        'warning': '价格更新失败，使用内置价格；新模型可能缺少价格。'}
