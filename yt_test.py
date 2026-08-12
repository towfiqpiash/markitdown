import requests
import re
import json
import codecs
import xml.etree.ElementTree as ET

url = "https://www.youtube.com/embed/M-uUFLU9IFU"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

res = requests.get(url, headers=headers)
html = res.text

print("Embed page GET status:", res.status_code, "HTML len:", len(html))

# Search for any player response JSON structure in embed HTML
matches = re.findall(r"window\.ytAtN\s*\(\s*{\s*['\"]R['\"]\s*:\s*['\"](.*?)['\"]\s*}\s*\)", html)
print("Regex matches count:", len(matches))

if not matches:
    # Try finding 'captionTracks' directly in html
    ct_matches = re.findall(r"\"captionTracks\":\s*(\[.*?\])", html)
    print("Direct captionTracks matches count:", len(ct_matches))
    if ct_matches:
        tracks = json.loads(ct_matches[0])
        print("Caption tracks count:", len(tracks))
        for t in tracks:
            print("  Track:", t.get("languageCode"), t.get("name", {}).get("simpleText"))
            base_url = t.get("baseUrl")
            if base_url:
                c_res = requests.get(base_url, headers=headers)
                root = ET.fromstring(c_res.text)
                lines = [elem.text for elem in root.iter("text") if elem.text]
                clean = [re.sub(r"<[^>]+>", "", text).replace("&amp;", "&").replace("&quot;", "\"") for text in lines]
                print(f"\n🎉 SUCCESS!! EXTRACTED {len(clean)} SPOKEN LINES!")
                print("SAMPLE SPOKEN TRANSCRIPT:\n", " ".join(clean[:50]))
                break
else:
    escaped_str = matches[0]
    json_str = codecs.decode(escaped_str, "unicode_escape")
    data = json.loads(json_str)
    captions = data.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
    print("Captions in player response:", len(captions))
    for t in captions:
        print("  Track:", t.get("languageCode"), t.get("name", {}).get("simpleText"))
        base_url = t.get("baseUrl")
        if base_url:
            c_res = requests.get(base_url, headers=headers)
            root = ET.fromstring(c_res.text)
            lines = [elem.text for elem in root.iter("text") if elem.text]
            clean = [re.sub(r"<[^>]+>", "", text).replace("&amp;", "&").replace("&quot;", "\"") for text in lines]
            print(f"\n🎉 SUCCESS!! EXTRACTED {len(clean)} SPOKEN LINES!")
            print("SAMPLE SPOKEN TRANSCRIPT:\n", " ".join(clean[:50]))
            break
