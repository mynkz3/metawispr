"""Check AMI range resolution, punctuation and complete source-word coverage."""

from collections import Counter
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from ami import NITE, referenced, render_words


def main():
    tree = ET.fromstring(f'<root xmlns:n="{NITE[1:-1]}"><section n:id="section">'
                         '<w n:id="w0">Hi</w><w n:id="w1">,</w>'
                         '<w n:id="w2">David</w><w n:id="w3">.</w></section></root>')
    words = referenced("test.xml#id(w0)..id(w3)", {"test.xml": tree})
    assert render_words(words) == "Hi, David."
    assert len(referenced("test.xml#id(w2)", {"test.xml": tree})) == 1
    try:
        referenced("test.xml#id(w3)..id(w0)", {"test.xml": tree})
    except ValueError:
        pass
    else:
        raise AssertionError("Reversed NXT range was accepted")
    root = Path(".cache/ami/es2002a")
    if (root / "manual-source-map.json").exists():
        mapping = json.loads((root / "manual-source-map.json").read_text(encoding="utf-8"))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        counts = Counter(word for item in mapping for word in item["word_ids"])
        assert len(mapping) == manifest["manual_segments"]
        assert len(counts) == manifest["lexical_tokens_with_punctuation"]
        assert set(counts.values()) == {1}
        assert all(a["start"] <= b["start"] for a, b in zip(mapping, mapping[1:]))
    print("AMI parser and source coverage checks passed")


if __name__ == "__main__":
    main()
