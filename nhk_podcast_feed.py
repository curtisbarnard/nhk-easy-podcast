#!/user/bin/env python3

import argparse
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape

SOURCE_FEED_URL = "https://nhkeasier.com/feed/"

NAMESPACES = {
    'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
    'atom': 'http://www.w3.org/2005/Atom'
}

def fetch_feed(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode('utf-8')

def extract_mp3_url(description: str) -> str | None:
    unescaped = unescape(description)
    match = re.search(r'<audio[^>]+src=["\']?([^"\'>\s]+\.mp3)', unescape, re.IGNORECASE)
    if match:
        mp3_path = match.group(1)
        if mp3_path.startswith('/'):
            return f"https://nhkeasier.com{mp3_path}"
        elif mp3_path.startswith('http'):
            return f"https://nhkeasier.com/{mp3_path}"
        return mp3_path
    return None

def get_mp3_size(url: str) -> int:
    try:
        request = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(request, timeout=30) as response:
            content_length = response.headers.get('Content-Length')
            if content_length:
                return int(content_length)
    except Exception:
        pass
    return 0

def transform_feed(source_xml: str) -> str:
    source_xml = re.sub(r'(\s+xmlns:itunes="[^"]*")(\s+xmlns:itunes="[^"]*")+', r'\1', source_xml)

    for prefix, uri in NAMESPACES.items():
        ET.register_namespace(prefix, uri)

    root = ET.fromstring(source_xml)
    channel = root.find('channel')

    if channel is None:
        print("Error: No channel element found in the feed.", file=sys.stderr)
        sys.exit(1)

    itunes_ns = NAMESPACES['itunes']

    if channel.find(f'{{{itunes_ns}}}author') is None:
        ET.SubElement(channel, f'{{{itunes_ns}}}author').text = "NHK Easier"
    if channel.find(f'{{{itunes_ns}}}summary') is None:
        ET.SubElement(channel, f'{{{itunes_ns}}}summary').text = "Audio version of NHK Easier articles"
    if channel.find(f'{{{itunes_ns}}}explicit') is None:
        ET.SubElement(channel, f'{{{itunes_ns}}}explicit').text = "no"
    if channel.find(f'{{{itunes_ns}}}category') is None:
        category = ET.SubElement(channel, f'{{{itunes_ns}}}category')
        category.set('text', 'News')

    items_to_remove = []
    for item in channel.findall('item'):
        description = item.find('description')
        if description is None or not description.text:
            items_to_remove.append(item)
            continue

        mp3_url = extract_mp3_url(description.text)
        if not mp3_url:
            items_to_remove.append(item)
            continue

        enclosure = item.find('enclosure')
        if enclosure is None:
            enclosure = ET.SubElement(item, 'enclosure')
            enclosure.set('url', mp3_url)
            enclosure.set('type', 'audio/mpeg')
            size = get_mp3_size(mp3_url)
            enclosure.set('length', str(size))

    for item in items_to_remove:
        channel.remove(item)

    print(f"Feed contains {len(channel.findall('item'))} items with audio", file=sys.stderr)

    return ET.tostring(root, encoding='unicode', xml_declaration=True)

def main():
    parser = argparse.ArgumentParser(description="Transform NHK Easier feed to include audio enclosure for podcast apps")
    parser.add_argument('--source-url', type=str, default=SOURCE_FEED_URL, help='URL of the source NHK Easier feed')
    parser.add_argument('--output-file', type=str, help='File to write the transformed feed to (defaults to stdout)')
    args = parser.parse_args()

    print(f"Fetching source feed from {args.source_url}", file=sys.stderr)
    source_xml = fetch_feed(args.source_url)

    print("Transforming feed...", file=sys.stderr)
    transformed_xml = transform_feed(source_xml)

    if args.output_file:
        with open(args.output_file, 'w', encoding='utf-8') as f:
            f.write(transformed_xml)
        print(f"Transformed feed written to {args.output_file}", file=sys.stderr)
    else:
        print(transformed_xml)

if __name__ == "__main__":
    main()