#!/usr/bin/env python3

import argparse
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape

SOURCE_FEED_URL = "https://nhkeasier.com/feed/"
BASE_URL = "https://nhkeasier.com"
BITRATE_BPS = 192000  # 192 kbps

NAMESPACES = {
    'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
    'atom': 'http://www.w3.org/2005/Atom'
}

def fetch_feed(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode('utf-8')

def extract_mp3_url(description: str) -> str | None:
    unescaped = unescape(description)
    match = re.search(r'<audio[^>]+src=["\']?([^"\'>\s]+\.mp3)', unescaped, re.IGNORECASE)
    if match:
        mp3_path = match.group(1)
        if mp3_path.startswith('/'):
            return f"{BASE_URL}{mp3_path}"
        return mp3_path
    return None

def fix_relative_urls(html_content: str) -> str:
    """Prepends BASE_URL to relative src and href attributes."""
    if not html_content:
        return html_content
    pattern = r'(src|href)=["\']/(?!/)([^"\']+)["\']'
    replacement = rf'\1="{BASE_URL}/\2"'
    return re.sub(pattern, replacement, html_content)

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

def format_duration(file_size_bytes: int) -> str:
    """Estimates duration in HH:MM:SS based on a fixed bitrate."""
    if file_size_bytes <= 0:
        return "00:00"
    
    # Calculation: (Bytes * 8 bits) / Bits per second
    total_seconds = int(file_size_bytes * 8 / BITRATE_BPS)
    
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    return f"{minutes:02}:{seconds:02}"

def transform_feed(source_xml: str) -> str:
    # Remove duplicate namespace declarations to keep the XML clean
    source_xml = re.sub(r'(\s+xmlns:itunes="[^"]*")(\s+xmlns:itunes="[^"]*")+', r'\1', source_xml)

    for prefix, uri in NAMESPACES.items():
        ET.register_namespace(prefix, uri)

    root = ET.fromstring(source_xml)
    channel = root.find('channel')

    if channel is None:
        print("Error: No channel element found.", file=sys.stderr)
        sys.exit(1)

    itunes_ns = NAMESPACES['itunes']

    # Set channel-level iTunes metadata
    tags = {
        'author': "NHK Easier",
        'summary': "Audio version of NHK Easier articles",
        'explicit': "no"
    }
    for tag, value in tags.items():
        if channel.find(f'{{{itunes_ns}}}{tag}') is None:
            ET.SubElement(channel, f'{{{itunes_ns}}}{tag}').text = value
            
    if channel.find(f'{{{itunes_ns}}}category') is None:
        category = ET.SubElement(channel, f'{{{itunes_ns}}}category')
        category.set('text', 'News')

    items_to_remove = []
    for item in channel.findall('item'):
        description_elem = item.find('description')
        if description_elem is None or not description_elem.text:
            items_to_remove.append(item)
            continue

        # 1. Update relative URLs in description
        description_elem.text = fix_relative_urls(description_elem.text)

        # 2. Extract MP3 for enclosure
        mp3_url = extract_mp3_url(description_elem.text)
        if not mp3_url:
            items_to_remove.append(item)
            continue

        file_size = get_mp3_size(mp3_url)

        # 3. Handle Enclosure
        enclosure = item.find('enclosure')
        if enclosure is None:
            enclosure = ET.SubElement(item, 'enclosure')
            enclosure.set('url', mp3_url)
            enclosure.set('type', 'audio/mpeg')
            enclosure.set('length', str(file_size))

        # 4. Corrected itunes:duration (Fixed the namespace string!)
        if item.find(f'{{{itunes_ns}}}duration') is None:
            duration_text = format_duration(file_size)
            ET.SubElement(item, f'{{{itunes_ns}}}duration').text = duration_text

    for item in items_to_remove:
        channel.remove(item)

    # Return as string with XML declaration
    return ET.tostring(root, encoding='unicode', xml_declaration=True)

def main():
    parser = argparse.ArgumentParser(description="NHK Easier Feed Transformer")
    parser.add_argument('--source-url', type=str, default=SOURCE_FEED_URL)
    parser.add_argument('--output-file', type=str)
    args = parser.parse_args()

    try:
        source_xml = fetch_feed(args.source_url)
        transformed_xml = transform_feed(source_xml)

        if args.output_file:
            with open(args.output_file, 'w', encoding='utf-8') as f:
                f.write(transformed_xml)
        else:
            print(transformed_xml)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()