"""Assemble the single-file map: src/explorer.html + src/model.js + src/findings.js + data/inv.json -> <slug>-system-map.html"""
import json, os, re

here = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(here, "tech-map.config.json")))
read = lambda p: open(os.path.join(here, p)).read()
title = f"{cfg['company']} System Map"
out = re.sub(r"[^a-z0-9]+", "-", cfg["company"].lower()).strip("-") + "-system-map.html"
html = read("src/explorer.html")
html = (html.replace("__TITLE__", title)
            .replace("<!--MODEL-->", "<script>\n" + read("src/model.js") + "\n</script>", 1)
            .replace("/*FINDINGS*/", read("src/findings.js"), 1)
            # Collected names come from the cloud (DNS records, comments…): keep "</script>" in them from closing the tag.
            .replace("/*INV*/null", read("data/inv.json").replace("</", "<\\/"), 1))
open(os.path.join(here, out), "w").write(html)
print("wrote", out, len(html), "bytes")
