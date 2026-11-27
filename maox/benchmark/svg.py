"""Keep model output inspectable while restricting previews to static SVG drawing."""
import re
import xml.etree.ElementTree as ET

SVG_NS = 'http://www.w3.org/2000/svg'
ALLOWED = set('svg g defs path rect circle ellipse line polyline polygon text tspan textPath '
              'linearGradient radialGradient stop clipPath mask pattern marker symbol use title desc '
              'filter feBlend feColorMatrix feComponentTransfer feComposite feConvolveMatrix '
              'feDiffuseLighting feDisplacementMap feDistantLight feDropShadow feFlood feFuncA '
              'feFuncB feFuncG feFuncR feGaussianBlur feMerge feMergeNode feMorphology '
              'feOffset fePointLight feSpecularLighting feSpotLight feTile feTurbulence style'.split())


def safe_svg_preview(reply: str) -> tuple[str, str]:
    match = re.search(r'<svg\b[^>]*>.*?</svg\s*>', reply, re.I | re.S)
    if not match:
        return '', '模型未返回完整 SVG；可查看原始回答。'
    source = match.group(0)
    if '<!ENTITY' in source.upper() or '<!DOCTYPE' in source.upper():
        return '', 'SVG 包含不支持的文档声明；可查看原始回答。'
    try:
        root = ET.fromstring(source)
    except (ET.ParseError, ValueError):
        return '', 'SVG 语法无效；可查看原始回答。'
    if root.tag not in {'svg', f'{{{SVG_NS}}}svg'}:
        return '', '模型未返回 SVG 根元素。'

    def safe_css(value):
        if '@' in value or re.search(r'expression\s*\(', value, re.I):
            return False
        return all(url.strip(' \t\r\n\'"').startswith('#')
                   for url in re.findall(r'url\s*\((.*?)\)', value, re.I | re.S))

    removed = False
    for element in list(root.iter()):
        for child in list(element):
            tag = child.tag.rsplit('}', 1)[-1]
            namespace = child.tag.split('}', 1)[0] if '}' in child.tag else ''
            if tag not in ALLOWED or namespace not in {'', '{' + SVG_NS}:
                element.remove(child)
                removed = True
        for key, value in list(element.attrib.items()):
            local = key.rsplit('}', 1)[-1].lower()
            if (local.startswith('on') or local in {'base', 'src'}
                    or (local == 'href' and not value.startswith('#'))
                    or not safe_css(value)):
                del element.attrib[key]
                removed = True
        if element.tag.rsplit('}', 1)[-1] == 'style' and not safe_css(element.text or ''):
            element.text = ''
            removed = True
    ET.register_namespace('', SVG_NS)
    if root.tag == 'svg':
        root.set('xmlns', SVG_NS)
    return ET.tostring(root, encoding='unicode'), ('预览已移除脚本、外部资源或非静态 SVG 内容；原始回答保留不变。' if removed else '')
