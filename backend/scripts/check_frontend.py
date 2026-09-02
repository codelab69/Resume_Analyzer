"""Section 6 of the Complete Testing Plan - the frontend - in a real browser.

Every other section of that plan can be run from a terminal. Section 6 could
not, so for a long time it was the part of the release checklist that got
reasoned about instead of measured, and four defects were sitting in it - two
of them things no amount of reading the source would have shown, because the
wrong colour came from the browser's own stylesheet rather than from this
repository. This script is what turns those rows into a command.

Start both halves first:

    uvicorn app.main:app --port 8000
    cd ../frontend && npm run dev -- --host 127.0.0.1

then:

    python scripts/check_frontend.py                  # chromium, every section
    python scripts/check_frontend.py --browser webkit # Safari's engine
    python scripts/check_frontend.py --only 6.4
    python scripts/check_frontend.py --mobile         # Pixel 7 and iPhone 14

Exits non-zero on any failure, so it gates like `e2e_check.py` does.

NOTHING HERE USES A TEST ID
---------------------------
The app has no `data-testid`, and none was added for this. Every element is
found by role, accessible name or visible text, so the accessibility layer has
to be working before a single check can even locate its target. A selector that
stops resolving is itself the finding.

WHY PLAYWRIGHT IS NOT IN requirements.txt
-----------------------------------------
It is a development tool and it drags three browser binaries behind it. The
application does not import it and a deployment does not need it. Install it
only when you are running this:

    pip install playwright
    playwright install chromium firefox webkit
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - the message is the whole point
    sys.exit(
        "Playwright is not installed, so the frontend cannot be driven.\n"
        "  pip install playwright\n"
        "  playwright install chromium firefox webkit\n"
        "It is deliberately not in requirements.txt: see this file's docstring."
    )

sys.stdout.reconfigure(encoding="utf-8")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIX = BACKEND_ROOT / "tests" / "fixtures"
BASE = "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000"

results: list[tuple[str, bool, str]] = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), str(detail)))
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  ({detail})" if detail else ""))
    return bool(cond)


def note(name, detail):
    results.append((name, None, str(detail)))
    print("  NOTE  " + name + (f"  ({detail})" if detail else ""))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def srgb(component: float) -> float:
    c = component / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    r, g, b = rgb
    return 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b)


def contrast(fg, bg) -> float:
    a, b = luminance(fg), luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def parse_rgb(value: str):
    nums = re.findall(r"[\d.]+", value or "")
    if len(nums) < 3:
        return None
    return tuple(float(n) for n in nums[:3])


# Contrast is computed in the page, not in Python. Tailwind v4 emits colours in
# `oklab(...)`, and a regex that assumes three 0-255 numbers reads
# `oklab(0.95 -0.004 0.006 / 0.9)` as rgb(0.95, -0.004, 0.006) - near-black -
# and reports the site header at 1.20:1. Painting each colour onto a canvas and
# reading the pixel back gets sRGB out of any syntax the browser accepts, which
# is the only way to be sure the number means what it says.
CONTRAST_JS = """
() => {
  const cv = document.createElement('canvas');
  cv.width = cv.height = 1;
  const cx = cv.getContext('2d', {willReadFrequently: true});
  const cache = new Map();
  const toRGBA = (css) => {
    if (cache.has(css)) return cache.get(css);
    cx.clearRect(0, 0, 1, 1);
    cx.fillStyle = '#000';
    cx.fillStyle = css;              // invalid values leave the previous fill
    cx.clearRect(0, 0, 1, 1);
    cx.fillRect(0, 0, 1, 1);
    const d = cx.getImageData(0, 0, 1, 1).data;
    const out = [d[0], d[1], d[2], d[3] / 255];
    cache.set(css, out);
    return out;
  };
  // Composite a translucent colour over what is behind it, as the compositor
  // does, rather than treating alpha 0.9 as if it were opaque.
  const over = (fg, bg) => [
    fg[0] * fg[3] + bg[0] * (1 - fg[3]),
    fg[1] * fg[3] + bg[1] * (1 - fg[3]),
    fg[2] * fg[3] + bg[2] * (1 - fg[3]),
    1,
  ];

  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const direct = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && n.textContent.trim())
      .map(n => n.textContent.trim()).join(' ');
    if (!direct) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || parseFloat(s.opacity) < 0.3) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;

    // Build the painted background by compositing every layer from the
    // outermost opaque ancestor back down to this element.
    const chain = [];
    for (let p = el; p; p = p.parentElement) chain.push(p);
    let bg = toRGBA(getComputedStyle(document.documentElement).backgroundColor);
    if (bg[3] < 1) bg = [255, 255, 255, 1];
    for (const node of chain.reverse()) {
      const ns = getComputedStyle(node);
      const layer = toRGBA(ns.backgroundColor);
      if (layer[3] > 0) bg = over(layer, bg);
      // A background-image with a solid stop paints over the colour. Report it
      // so the caller can see when a gradient is doing the work.
      if (ns.backgroundImage && ns.backgroundImage !== 'none' && node === el) {
        out.hasImage = true;
      }
    }
    out.push({
      text: direct.slice(0, 40),
      tag: el.tagName.toLowerCase(),
      cls: (el.className || '').toString().slice(0, 30),
      fg: toRGBA(s.color),
      bg: bg,
      bgImage: (s.backgroundImage || 'none').slice(0, 60),
      size: parseFloat(s.fontSize),
      weight: s.fontWeight,
    });
  }
  return out;
}
"""


def upload_resume(page, path: Path = FIX / "sample_resume.txt") -> str:
    """Upload through the UI and return the resume id from the URL."""
    page.goto(f"{BASE}/upload", wait_until="networkidle")
    page.locator("input[type=file]").set_input_files(str(path))
    page.wait_for_url(re.compile(r"/report/[0-9a-f]+"), timeout=60_000)
    return page.url.rsplit("/", 1)[-1]


def no_horizontal_scroll(page) -> tuple[bool, str]:
    over = page.evaluate("""() => {
      const d = document.documentElement;
      const wide = [];
      if (d.scrollWidth > d.clientWidth + 1) {
        for (const el of document.querySelectorAll('body *')) {
          const r = el.getBoundingClientRect();
          if (r.right > d.clientWidth + 1 || r.left < -1) {
            wide.push(el.tagName.toLowerCase() + '.' +
                      (el.className || '').toString().split(' ')[0] +
                      ' [' + Math.round(r.left) + '..' + Math.round(r.right) + ']');
          }
        }
      }
      return {scroll: d.scrollWidth, client: d.clientWidth, offenders: wide.slice(0, 4)};
    }""")
    ok = over["scroll"] <= over["client"] + 1
    return ok, f"scrollWidth {over['scroll']} vs clientWidth {over['client']}" + (
        f", first offenders: {over['offenders']}" if over["offenders"] else "")


# ---------------------------------------------------------------------------
# 6.1 Screens
# ---------------------------------------------------------------------------

def section_6_1(page, rid):
    print("\n--- 6.1 Screens: loads / empty / error / mobile ---")
    screens = [
        ("Landing", "/", None),
        ("Upload", "/upload", None),
        ("Report", f"/report/{rid}", None),
        ("Match", f"/match/{rid}", None),
        ("Openings", f"/jobs/{rid}", None),
        ("History", "/dashboard", None),
    ]
    for label, path, _ in screens:
        page.set_viewport_size({"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{BASE}{path}", wait_until="networkidle")
        h1 = page.locator("h1")
        check(f"{label} loads", h1.count() == 1 and not errors,
              f"h1={h1.first.inner_text()[:38]!r}" + (f" errors={errors}" if errors else ""))
        page.remove_listener("pageerror", lambda e: None) if False else None

        page.set_viewport_size({"width": 360, "height": 780})
        page.goto(f"{BASE}{path}", wait_until="networkidle")
        ok, detail = no_horizontal_scroll(page)
        check(f"{label} at 360 px: no horizontal scroll", ok, detail)
    page.set_viewport_size({"width": 1280, "height": 900})

    print("\n  empty states")
    page.goto(f"{BASE}/upload", wait_until="networkidle")
    check("Upload empty state is the dropzone",
          page.get_by_text("Drag a resume here").is_visible())

    page.goto(f"{BASE}/match/{rid}", wait_until="networkidle")
    body = page.inner_text("main")
    check("Match empty state before a JD is pasted",
          "paste" in body.lower() or "job description" in body.lower(), body[:70].replace("\n", " "))

    page.goto(f"{BASE}/jobs/{rid}?location=Bengaluru&category=Nonexistent", wait_until="networkidle")
    page.wait_for_timeout(1200)
    body = page.inner_text("main")
    check("Openings empty state on an impossible filter, not an error",
          ("no " in body.lower() or "nothing" in body.lower() or "0 " in body)
          and "error" not in body.lower(),
          body[-160:].replace("\n", " ").strip()[:110])

    print("\n  error states")
    page.goto(f"{BASE}/report/deadbeefdeadbeef", wait_until="networkidle")
    page.wait_for_timeout(1500)
    body = page.inner_text("main")
    check("Report error state on an unknown id",
          "could not be found" in body.lower() or "not found" in body.lower(),
          body[:110].replace("\n", " "))
    check("  and it is not a blank screen or a stack trace",
          "Traceback" not in body and len(body.strip()) > 20, f"{len(body)} chars")

    page.goto(f"{BASE}/match/deadbeefdeadbeef", wait_until="networkidle")
    page.wait_for_timeout(1500)
    body = page.inner_text("main")
    check("Match error state on an unknown id",
          "could not be found" in body.lower() or "not found" in body.lower(),
          body[:110].replace("\n", " "))

    page.goto(f"{BASE}/jobs/deadbeefdeadbeef", wait_until="networkidle")
    page.wait_for_timeout(1500)
    body = page.inner_text("main")
    check("Openings error state on an unknown id",
          "could not be found" in body.lower() or "not found" in body.lower(),
          body[:110].replace("\n", " "))


# ---------------------------------------------------------------------------
# 6.2 Behaviour
# ---------------------------------------------------------------------------

def section_6_2(page, rid):
    print("\n--- 6.2 Behaviour ---")

    # click-to-browse
    page.goto(f"{BASE}/upload", wait_until="networkidle")
    page.locator("input[type=file]").set_input_files(str(FIX / "sample_resume.txt"))
    page.wait_for_url(re.compile(r"/report/[0-9a-f]+"), timeout=60_000)
    check("click-to-browse accepts a file", "/report/" in page.url, page.url.split("/")[-1][:12])

    # drag and drop - a real DataTransfer, dispatched as the browser would
    page.goto(f"{BASE}/upload", wait_until="networkidle")
    text = (FIX / "sample_resume.txt").read_text(encoding="utf-8")
    page.evaluate("""(content) => {
      // dataTransfer is read-only on a constructed DragEvent, so it has to go
      // in through the constructor rather than be assigned afterwards.
      const file = new File([content], 'dropped.txt', {type: 'text/plain'});
      const dt = new DataTransfer();
      dt.items.add(file);
      // react-dropzone binds its handlers to the element getRootProps() is
      // spread onto - the div wrapping the animated surface. Dispatching on
      // the hidden input and letting the event bubble reaches it either way.
      const input = document.querySelector('input[type=file]');
      const zone = input.parentElement.parentElement;
      for (const type of ['dragenter', 'dragover', 'drop']) {
        zone.dispatchEvent(new DragEvent(type, {
          bubbles: true, cancelable: true, dataTransfer: dt,
        }));
      }
    }""", text)
    try:
        page.wait_for_url(re.compile(r"/report/[0-9a-f]+"), timeout=30_000)
        check("drag and drop accepts a file", True, page.url.split("/")[-1][:12])
    except Exception:
        check("drag and drop accepts a file", False,
              f"still on {page.url}; the drop handler did not fire")

    # unsupported type -> inline error, no navigation, no download
    page.goto(f"{BASE}/upload", wait_until="networkidle")
    downloads = []
    page.on("download", lambda d: downloads.append(d.suggested_filename))
    bad = Path("C:/Users/ASUS/AppData/Local/Temp/claude/D--Ai-Resume/"
               "2cfa4ec7-1a78-4174-9f37-2ff3ef901fbf/scratchpad/not_a_resume.png")
    bad.write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64)
    page.locator("input[type=file]").set_input_files(str(bad))
    page.wait_for_timeout(2500)
    alert = page.locator("[role=alert]")
    check("dropping an unsupported type shows the inline error",
          alert.count() > 0 and alert.first.is_visible(),
          alert.first.inner_text()[:90].replace("\n", " ") if alert.count() else "no [role=alert]")
    check("  and does not navigate away from /upload", "/upload" in page.url, page.url)
    check("  and does not trigger a browser download", not downloads, str(downloads))

    # The stepper. On localhost the whole upload takes ~55 ms, so there is
    # nothing to watch unless the transport is slowed down. Throttling through
    # CDP rather than sleeping in a route handler: the sync API runs route
    # handlers on the loop that drives the page, so a sleeping handler freezes
    # the very thing being sampled.
    stages_seen, order = {}, []
    if page.context.browser.browser_type.name == "chromium":
        page.goto(f"{BASE}/upload", wait_until="networkidle")
        cdp = page.context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.emulateNetworkConditions", {
            "offline": False, "latency": 1200,
            "downloadThroughput": 12_000, "uploadThroughput": 12_000})
        page.locator("input[type=file]").set_input_files(str(FIX / "sample_resume.txt"))
        deadline = time.time() + 30
        while time.time() < deadline and "/report/" not in page.url:
            try:
                if page.get_by_text("Analysing").count():
                    active = page.evaluate("""() => {
                      const li = document.querySelectorAll('ol li');
                      for (let i = 0; i < li.length; i++) {
                        const s = getComputedStyle(li[i].querySelector('span:nth-child(2)'));
                        if (parseInt(s.fontWeight, 10) >= 600)
                          return {i, name: li[i].innerText.trim()};
                      }
                      return null;
                    }""")
                    if active and active["i"] not in stages_seen:
                        stages_seen[active["i"]] = active["name"]
                        order.append(active["i"])
            except Exception:
                pass
            page.wait_for_timeout(120)
        cdp.send("Network.emulateNetworkConditions", {
            "offline": False, "latency": 0,
            "downloadThroughput": -1, "uploadThroughput": -1})

        check("the analysis stepper advances", len(order) > 1 and order == sorted(order),
              f"stages {order} -> {[stages_seen[i] for i in order]}")
        check("  and it stops at the last stage rather than completing early",
              bool(stages_seen) and max(stages_seen) == 5,
              f"highest stage reached while waiting: {max(stages_seen) if stages_seen else '-'} of 5")
        check("  and the final step waits for the real response - the report "
              "URL only appears after the API answers",
              "/report/" in page.url, "/".join(page.url.split("/")[-2:]))
    else:
        note("the analysis stepper advances",
             "CDP throttling is chromium-only; measured there")
        page.goto(f"{BASE}/upload", wait_until="networkidle")
        page.locator("input[type=file]").set_input_files(str(FIX / "sample_resume.txt"))
        page.wait_for_url(re.compile(r"/report/[0-9a-f]+"), timeout=60_000)
        check("  and the final step waits for the real response - the report "
              "URL only appears after the API answers",
              "/report/" in page.url, "/".join(page.url.split("/")[-2:]))

    # a failed upload must not leave the stepper claiming success
    page.goto(f"{BASE}/upload", wait_until="networkidle")
    page.locator("input[type=file]").set_input_files(str(bad))
    page.wait_for_timeout(2500)
    check("a failed upload stops the stepper - it never shows 'done' after an error",
          page.get_by_text("Analysing").count() == 0 and page.locator("[role=alert]").count() > 0,
          f"stepper visible={page.get_by_text('Analysing').count() > 0}")

    # skill highlights and chips
    page.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
    page.wait_for_timeout(1200)
    marks = page.locator("mark, .mark, [class*='mark']")
    highlighted = page.evaluate("""() => {
      const els = document.querySelectorAll('mark');
      return Array.from(els).slice(0, 200).map(e => e.textContent.trim());
    }""")
    check("skill highlights are rendered in the resume text",
          len(highlighted) > 0, f"{len(highlighted)} marks, first: {highlighted[:5]}")

    import httpx
    api = httpx.get(f"{API}/api/resume/{rid}", timeout=60).json()
    resume_text = api["text"]
    spans_ok = all(
        resume_text[s["start"]:s["end"]].lower() == s["surface"].lower()
        for s in api["skills"]
    )
    check("  and every span the API returned slices back to its own surface",
          spans_ok, f"{len(api['skills'])} spans")
    rendered_ok = all(any(h.lower() == s["surface"].lower() for h in highlighted)
                      for s in api["skills"][:20])
    check("  and the highlighted words are the ones the API marked",
          rendered_ok,
          f"{len(set(h.lower() for h in highlighted))} distinct highlighted strings")

    chips = page.locator("button[aria-pressed]")
    n_chips = chips.count()
    check("skill chips are rendered", n_chips > 0, f"{n_chips} chips")
    if n_chips:
        first = chips.first
        name = first.inner_text()
        first.click()
        page.wait_for_timeout(400)
        check("clicking a skill chip sets it pressed",
              first.get_attribute("aria-pressed") == "true", f"{name!r}")
        after = page.evaluate("""() => Array.from(document.querySelectorAll('mark'))
                                  .filter(m => getComputedStyle(m).opacity > 0.5).length""")
        check("  and isolates it in the text",
              page.get_by_text(re.compile(r"CLEAR FILTER")).count() > 0,
              f"{after} marks still emphasised")
        page.get_by_text(re.compile(r"CLEAR FILTER")).first.click()
        page.wait_for_timeout(400)
        check("  and clearing the filter restores all highlights",
              first.get_attribute("aria-pressed") == "false"
              and page.get_by_text(re.compile(r"CLEAR FILTER")).count() == 0)

    fuzzy = [s for s in api["skills"] if s.get("method") == "fuzzy"]
    if fuzzy:
        styled = page.evaluate("""() => Array.from(document.querySelectorAll('mark'))
            .filter(m => (m.style.textDecoration || '').includes('dotted')
                      || getComputedStyle(m).textDecorationStyle === 'dotted').length""")
        check("fuzzy matches are visibly distinguished (dotted underline)",
              styled > 0, f"{len(fuzzy)} fuzzy spans, {styled} dotted in the DOM")
    else:
        note("fuzzy matches are visibly distinguished",
             "this resume produced no fuzzy matches - not exercised")

    # ATS rules open by default when they lost points
    expanders = page.locator("button[aria-expanded]")
    states = []
    for i in range(expanders.count()):
        el = expanders.nth(i)
        txt = el.inner_text()
        states.append((txt.split("\n")[0][:40], el.get_attribute("aria-expanded"), txt))
    lost = [s for s in states if re.search(r"(\d+(?:\.\d+)?)/(\d+)", s[2])
            and float(re.search(r"(\d+(?:\.\d+)?)/(\d+)", s[2]).group(1))
              < float(re.search(r"(\d+(?:\.\d+)?)/(\d+)", s[2]).group(2))]
    full = [s for s in states if s not in lost]
    check("ATS rules that lost points are open by default",
          bool(lost) and all(s[1] == "true" for s in lost),
          f"{len(lost)} losing rules, expanded={[s[1] for s in lost]}")
    check("  and rules at full marks are collapsed",
          all(s[1] == "false" for s in full) if full else True,
          f"{len(full)} full-mark rules, expanded={[s[1] for s in full]}")

    # job filters live in the URL and survive a refresh
    page.goto(f"{BASE}/jobs/{rid}", wait_until="networkidle")
    page.wait_for_timeout(1500)
    selects = page.locator("select")
    check("Openings has filter controls", selects.count() >= 1, f"{selects.count()} selects")
    if selects.count():
        options = page.evaluate("""() => Array.from(document.querySelectorAll('select'))
            .map(s => ({name: s.previousElementSibling?.textContent || s.name,
                        values: Array.from(s.options).map(o => o.value).filter(Boolean)}))""")
        target = next((o for o in options if o["values"]), None)
        if target:
            value = target["values"][0]
            idx = options.index(target)
            selects.nth(idx).select_option(value)
            page.wait_for_timeout(1200)
            check("choosing a filter puts it in the URL", value in page.url, page.url.split("?")[-1])
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(1200)
            check("  and the filter survives a page refresh",
                  selects.nth(idx).input_value() == value,
                  f"{selects.nth(idx).input_value()!r} after reload")

    # a report URL pasted into a new tab
    context = page.context
    fresh = context.new_page()
    fresh.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
    fresh.wait_for_timeout(1500)
    check("a report URL can be pasted into a new tab and loads",
          fresh.locator("h1").count() == 1
          and "could not be found" not in fresh.inner_text("main").lower(),
          fresh.locator("h1").first.inner_text()[:40])
    fresh.close()

    # deleting the active resume clears the scoped nav links
    page.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
    page.wait_for_timeout(800)
    before = page.locator("nav[aria-label='Main'] a").all_inner_texts()
    check("scoped nav links are present while a resume is loaded",
          "Report" in before and "Job match" in before and "Openings" in before, str(before))
    page.goto(f"{BASE}/dashboard", wait_until="networkidle")
    page.wait_for_timeout(1200)
    del_buttons = page.get_by_role("button", name=re.compile(r"delete|remove", re.I))
    if del_buttons.count():
        page.once("dialog", lambda d: d.accept())
        del_buttons.first.click()
        page.wait_for_timeout(1800)
        after = page.locator("nav[aria-label='Main'] a").all_inner_texts()
        check("deleting the active resume clears the scoped nav links",
              "Report" not in after and "Job match" not in after and "Openings" not in after,
              str(after))
    else:
        note("deleting the active resume clears the scoped nav links",
             "no delete control found on /dashboard by accessible name")


# ---------------------------------------------------------------------------
# 6.3 Themes and motion
# ---------------------------------------------------------------------------

def section_6_3(page, rid):
    print("\n--- 6.3 Themes and motion ---")
    for theme in ("light", "dark"):
        page.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
        page.evaluate("(t) => localStorage.setItem('resume-analyzer:theme', t)", theme)
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1200)
        is_dark = "dark" in (page.locator("html").get_attribute("class") or "")
        check(f"{theme} theme is applied", is_dark == (theme == "dark"),
              f"html class={page.locator('html').get_attribute('class')!r}")

        pairs = page.evaluate(CONTRAST_JS)
        bad = []
        for item in pairs:
            fg, bg = item["fg"][:3], item["bg"][:3]
            ratio = contrast(fg, bg)
            large = item["size"] >= 24 or (item["size"] >= 18.66
                                           and int(item["weight"] or 400) >= 700)
            floor = 3.0 if large else 4.5
            if ratio < floor:
                bad.append(f"{item['tag']}.{item['cls'].split()[0] if item['cls'] else ''} "
                           f"{item['text'][:24]!r} {ratio:.2f} (needs {floor})")
        worst = sorted(
            ((contrast(i["fg"][:3], i["bg"][:3]), i) for i in pairs),
            key=lambda t: t[0])[:3]
        check(f"{theme} theme: every text/background pair meets WCAG AA",
              not bad,
              f"{len(pairs)} pairs checked; lowest {worst[0][0]:.2f} on "
              f"{worst[0][1]['text'][:24]!r}"
              + (f"; {len(bad)} below AA: {bad[:3]}" if bad else ""))

    # persistence
    page.evaluate("() => localStorage.setItem('resume-analyzer:theme', 'dark')")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(600)
    check("theme choice survives a refresh",
          "dark" in (page.locator("html").get_attribute("class") or ""),
          page.locator("html").get_attribute("class"))

    # the toggle itself
    toggle = page.get_by_role("button", name=re.compile(r"switch to .* theme", re.I))
    check("the theme toggle is reachable by its accessible name", toggle.count() == 1,
          toggle.first.get_attribute("aria-label") if toggle.count() else "not found")
    if toggle.count():
        toggle.first.click()
        page.wait_for_timeout(500)
        check("  and it switches the theme",
              "dark" not in (page.locator("html").get_attribute("class") or ""),
              page.locator("html").get_attribute("class"))

    # score gauge must not overshoot
    page.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
    peak = page.evaluate("""() => new Promise(resolve => {
      let max = 0;
      const read = () => {
        for (const el of document.querySelectorAll('[role=img][aria-label]')) {
          const m = (el.getAttribute('aria-label') || '').match(/(\\d+) out of 100/);
          if (m) max = Math.max(max, parseInt(m[1], 10));
        }
        for (const el of document.querySelectorAll('*')) {
          const t = (el.childNodes.length === 1 && el.firstChild.nodeType === 3)
            ? el.textContent.trim() : '';
          if (/^\\d{1,3}$/.test(t)) max = Math.max(max, parseInt(t, 10));
        }
      };
      const id = setInterval(read, 16);
      setTimeout(() => { clearInterval(id); resolve(max); }, 2500);
    })""")
    check("the score gauge never overshoots past 100", peak <= 100, f"peak rendered value {peak}")


def section_6_3_motion(browser, rid):
    print("\n  reduced motion")
    ctx = browser.new_context(reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
    page.wait_for_timeout(400)
    moving = page.evaluate("""() => {
      const el = document.querySelectorAll('*');
      const before = [...el].map(e => e.getBoundingClientRect().top);
      return new Promise(res => setTimeout(() => {
        const after = [...el].map(e => e.getBoundingClientRect().top);
        let n = 0;
        for (let i = 0; i < before.length; i++)
          if (Math.abs(before[i] - after[i]) > 1) n++;
        res(n);
      }, 700));
    }""")
    check("with reduce-motion on, nothing is still animating after first paint",
          moving == 0, f"{moving} elements moved in a 700 ms window")
    opacities = page.evaluate("""() => {
      let faded = 0;
      for (const e of document.querySelectorAll('body *')) {
        const o = parseFloat(getComputedStyle(e).opacity);
        const r = e.getBoundingClientRect();
        if (r.width > 1 && r.height > 1 && o > 0 && o < 0.99) faded++;
      }
      return faded;
    }""")
    check("  and every element is at its final state, not mid-fade",
          opacities == 0, f"{opacities} elements at a partial opacity")
    # The reduce-motion block sets 0.01ms rather than 0s. That is deliberate and
    # standard: a genuinely zero duration stops `transitionend` from firing at
    # all, which breaks any code waiting on it. Anything at or under 0.02ms is
    # imperceptible, so that is the bar rather than an exact zero.
    transitions = page.evaluate("""() => {
      const slow = [];
      const secs = (v) => v.trim().endsWith('ms')
        ? parseFloat(v) / 1000 : parseFloat(v);
      for (const e of document.querySelectorAll('body *')) {
        const s = getComputedStyle(e);
        for (const d of (s.transitionDuration || '').split(','))
          if (secs(d) > 0.00002) slow.push(e.tagName.toLowerCase() + ' ' + d.trim());
        for (const d of (s.animationDuration || '').split(','))
          if (secs(d) > 0.00002) slow.push(e.tagName.toLowerCase() + ' anim ' + d.trim());
      }
      return slow.slice(0, 5);
    }""")
    check("  and every CSS transition and animation is cut to an imperceptible "
          "duration (0.01 ms, not 0, so transitionend still fires)",
          not transitions, str(transitions))
    ctx.close()


def section_6_3_flash(browser, rid):
    print("\n  flash of the wrong theme")
    ctx = browser.new_context(color_scheme="dark")
    page = ctx.new_page()

    # Hold the module that applies the theme, so the window between first paint
    # and `applyTheme()` is long enough to photograph. If the page is light in
    # that window, a real user on a slow connection sees the same thing.
    def delay(route):
        time.sleep(0.6)
        route.continue_()

    page.route(re.compile(r"/src/main\.tsx"), delay)
    page.goto(f"{BASE}/report/{rid}", wait_until="commit")
    page.wait_for_timeout(300)
    early = page.evaluate("""() => ({
      html: document.documentElement.className,
      body: getComputedStyle(document.body).backgroundColor,
      scheme: getComputedStyle(document.documentElement).colorScheme,
    })""")
    page.wait_for_timeout(2500)
    late = page.evaluate("""() => ({
      html: document.documentElement.className,
      body: getComputedStyle(document.body).backgroundColor,
    })""")
    early_rgb, late_rgb = parse_rgb(early["body"]), parse_rgb(late["body"])
    flashed = (early_rgb and late_rgb
               and abs(luminance(early_rgb) - luminance(late_rgb)) > 0.25)
    check("no flash of the wrong theme on load (OS set to dark, JS held 600 ms)",
          not flashed,
          f"before JS: {early['body']} class={early['html']!r}; after: {late['body']} class={late['html']!r}")
    ctx.close()


# ---------------------------------------------------------------------------
# 6.4 Accessibility
# ---------------------------------------------------------------------------

def section_6_4(page, rid):
    print("\n--- 6.4 Accessibility ---")
    page.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
    page.wait_for_timeout(1200)

    interactive = page.evaluate("""() => {
      const sel = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])';
      return Array.from(document.querySelectorAll(sel))
        .filter(e => {
          const r = e.getBoundingClientRect();
          const s = getComputedStyle(e);
          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && !e.disabled;
        })
        .map(e => e.tagName.toLowerCase() + (e.type ? '[' + e.type + ']' : '')
                  + ':' + (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 20));
    }""")
    # Tab until the focus ring has been all the way round and come back to
    # where it started. Stopping after len(interactive) presses is wrong: the
    # count includes duplicates, so the loop can hit its budget while elements
    # further down the order have never been focused.
    reached: list[str] = []
    page.evaluate("() => document.body.focus()")
    first_seen = None
    for i in range(len(interactive) * 2 + 30):
        page.keyboard.press("Tab")
        who = page.evaluate("""() => {
          const e = document.activeElement;
          if (!e || e === document.body) return null;
          return e.tagName.toLowerCase() + (e.type ? '[' + e.type + ']' : '')
                 + ':' + (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 20);
        }""")
        if not who:
            continue
        if first_seen is None:
            first_seen = who
        elif who == first_seen and len(reached) > 1:
            break                      # wrapped round to the start
        reached.append(who)
    missed = [x for x in interactive if x not in reached]
    engine = page.context.browser.browser_type.name
    # Safari leaves links out of sequential focus navigation unless the user
    # turns on "Press Tab to highlight each item on a webpage", which is off by
    # default; Playwright's WebKit build inherits that. Measured directly: on
    # this page WebKit tabs the 30 buttons and none of the 8 anchors, while
    # Chromium tabs both. A platform default, not a defect in this app - but
    # only reportable as such when every missed element really is a link.
    if engine == "webkit" and missed and all(m.startswith("a:") for m in missed):
        note("every interactive element is reachable by Tab",
             f"WebKit: {len(interactive) - len(missed)} of {len(interactive)} reached; "
             f"the {len(missed)} skipped are all links, which is Safari's default "
             f"tab behaviour rather than an app defect")
    else:
        check("every interactive element is reachable by Tab",
              not missed, f"{len(interactive)} interactive, {len(set(reached))} reached"
                          + (f", missed: {missed[:4]}" if missed else ""))

    invisible = page.evaluate("""() => {
      const sel = 'a[href], button, input, select, textarea';
      const bad = [];
      for (const e of document.querySelectorAll(sel)) {
        const r = e.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        e.focus();
        const s = getComputedStyle(e);
        const outline = parseFloat(s.outlineWidth) > 0 && s.outlineStyle !== 'none';
        const ring = (s.boxShadow || 'none') !== 'none';
        const border = (s.borderColor || '');
        if (!outline && !ring) {
          bad.push(e.tagName.toLowerCase() + ':' +
                   (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 24));
        }
      }
      return bad;
    }""")
    check("a focus outline is visible on every focused element",
          not invisible, f"{len(invisible)} without an outline or ring"
                         + (f": {invisible[:4]}" if invisible else ""))

    gauge = page.locator("[role=img][aria-label]")
    labels = [gauge.nth(i).get_attribute("aria-label") for i in range(gauge.count())]
    check("the score gauge has an accessible label reading the value",
          any(re.search(r"\d+ out of 100", l or "") for l in labels), str(labels[:2]))

    page.goto(f"{BASE}/match/{rid}", wait_until="networkidle")
    # The posting is the textarea; the single-line input above it is the
    # optional title. Filling the wrong one leaves the button disabled, because
    # the posting is still under the 40-character floor.
    page.locator("textarea").first.fill(
        (FIX / "backend_jd.txt").read_text(encoding="utf-8"))
    submit = page.get_by_role("button", name=re.compile(r"score this match", re.I))
    check("the match button is enabled once a long enough posting is pasted",
          submit.count() == 1 and submit.first.is_enabled(),
          "enabled" if submit.count() and submit.first.is_enabled() else "still disabled")
    if submit.count() and submit.first.is_enabled():
        submit.first.click()
        page.wait_for_selector("[role=meter]", timeout=60_000)
    meters = page.locator("[role=meter]")
    ok_meters = []
    for i in range(meters.count()):
        m = meters.nth(i)
        now = m.get_attribute("aria-valuenow")
        lo = m.get_attribute("aria-valuemin")
        hi = m.get_attribute("aria-valuemax")
        ok_meters.append(now is not None and lo == "0" and hi == "100"
                         and 0 <= float(now) <= 100)
    check("sub-score bars expose role=meter with correct values",
          meters.count() >= 4 and all(ok_meters),
          f"{meters.count()} meters, valid={sum(ok_meters)}")

    page.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
    page.wait_for_timeout(1000)
    expanders = page.locator("button[aria-expanded]")
    check("expandable rules set aria-expanded",
          expanders.count() >= 10
          and all(expanders.nth(i).get_attribute("aria-expanded") in ("true", "false")
                  for i in range(expanders.count())),
          f"{expanders.count()} expandable buttons")

    page.goto(f"{BASE}/jobs/{rid}", wait_until="networkidle")
    page.wait_for_timeout(1800)
    job_exp = page.locator("button[aria-expanded]")
    check("expandable job cards set aria-expanded", job_exp.count() > 0,
          f"{job_exp.count()} on Openings")

    for label, path in [("Landing", "/"), ("Upload", "/upload"),
                        ("Report", f"/report/{rid}"), ("Match", f"/match/{rid}"),
                        ("Openings", f"/jobs/{rid}"), ("History", "/dashboard")]:
        page.goto(f"{BASE}{path}", wait_until="networkidle")
        page.wait_for_timeout(400)
        check(f"{label} has exactly one h1", page.locator("h1").count() == 1,
              f"{page.locator('h1').count()} h1 elements")

    # colour is never the only signal
    page.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
    page.wait_for_timeout(1200)
    statuses = page.evaluate("""() => {
      // Every rule row: does it carry a word for its state, or only a colour?
      const rows = [];
      for (const b of document.querySelectorAll('button[aria-expanded]')) {
        const t = b.innerText;
        rows.push({
          text: t.slice(0, 60).replace(/\\n/g, ' '),
          hasNumber: /\\d+(\\.\\d+)?\\/\\d+/.test(t),
        });
      }
      return rows;
    }""")
    check("status is never signalled by colour alone - every rule row carries its score",
          statuses and all(r["hasNumber"] for r in statuses),
          f"{len(statuses)} rows, {sum(1 for r in statuses if r['hasNumber'])} carry a number")

    note("Lighthouse accessibility score >= 90",
         "not run - Lighthouse is a Chrome-only tool and is not installed. "
         "The individual rows it would cover are measured above.")


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def run(browser_name: str, only: str | None):
    with sync_playwright() as p:
        launcher = {"chromium": p.chromium, "firefox": p.firefox, "webkit": p.webkit}[browser_name]
        browser = launcher.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        print(f"\n{'=' * 74}\n  {browser_name.upper()}  -  {BASE}\n{'=' * 74}")
        rid = upload_resume(page)
        print(f"  resume under test: {rid}\n")

        if only in (None, "6.1"):
            section_6_1(page, rid)
        if only in (None, "6.2"):
            section_6_2(page, upload_resume(page))
        if only in (None, "6.3"):
            rid3 = upload_resume(page)
            section_6_3(page, rid3)
            section_6_3_motion(browser, rid3)
            section_6_3_flash(browser, rid3)
        if only in (None, "6.4"):
            section_6_4(page, upload_resume(page))

        ctx.close()
        browser.close()


def run_mobile():
    """6.5's two phone rows, on device profiles rather than a narrow window.

    A resized desktop window is not a phone: it keeps the desktop user agent, a
    mouse pointer and a device pixel ratio of 1. The device descriptors carry
    the real UA string, touch support and DPR, which is what decides whether a
    hover-only affordance or an undersized tap target actually bites.
    """
    with sync_playwright() as p:
        for engine, device in (("chromium", "Pixel 7"), ("webkit", "iPhone 14")):
            browser = getattr(p, engine).launch()
            ctx = browser.new_context(**p.devices[device])
            page = ctx.new_page()
            vp = page.viewport_size
            print(f"\n--- {device} on {engine} "
                  f"({vp['width']}x{vp['height']}, DPR "
                  f"{p.devices[device]['device_scale_factor']}, touch) ---")

            rid = upload_resume(page)
            check(f"{device}: upload works end to end on a touch device", bool(rid), rid[:12])

            for label, path in [("Landing", "/"), ("Upload", "/upload"),
                                ("Report", f"/report/{rid}"), ("Match", f"/match/{rid}"),
                                ("Openings", f"/jobs/{rid}"), ("History", "/dashboard")]:
                page.goto(f"{BASE}{path}", wait_until="networkidle")
                page.wait_for_timeout(900)
                ok, detail = no_horizontal_scroll(page)
                check(f"{device}: {label} has no horizontal scroll", ok, detail)

            check(f"{device}: the browser reports a no-hover pointer",
                  page.evaluate("() => matchMedia('(hover: none)').matches"))

            # WCAG 2.2 SC 2.5.8 asks for 24x24 CSS px on anything tappable.
            page.goto(f"{BASE}/report/{rid}", wait_until="networkidle")
            page.wait_for_timeout(1200)
            small = page.evaluate("""() => {
              const out = [];
              for (const e of document.querySelectorAll('a[href], button')) {
                const r = e.getBoundingClientRect();
                if (r.width < 1 || r.height < 1) continue;
                if (r.height < 24 || r.width < 24)
                  out.push((e.textContent || e.getAttribute('aria-label') || '?')
                             .trim().slice(0, 18)
                           + ' ' + r.width.toFixed(1) + 'x' + r.height.toFixed(1));
              }
              return out;
            }""")
            if small:
                note(f"{device}: tap targets under the WCAG 2.2 minimum of 24x24",
                     f"{len(small)} under size, e.g. {small[:3]} - open as S7.1l, "
                     f"a design call rather than a defect fix")
            else:
                check(f"{device}: every tap target clears 24x24 CSS px", True)
            ctx.close()
            browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default="chromium",
                    choices=["chromium", "firefox", "webkit"])
    ap.add_argument("--only", default=None)
    ap.add_argument("--mobile", action="store_true",
                    help="Run 6.5's phone rows on Pixel 7 and iPhone 14 profiles.")
    args = ap.parse_args()
    if args.mobile:
        run_mobile()
    else:
        run(args.browser, args.only)

    passed = sum(1 for _, ok, _ in results if ok is True)
    failed = [(n, d) for n, ok, d in results if ok is False]
    noted = sum(1 for _, ok, _ in results if ok is None)
    print(f"\n{'=' * 74}")
    print(f"  {passed} passed, {len(failed)} failed, {noted} noted")
    for n, d in failed:
        print(f"  FAIL  {n}  ({d})")
    sys.exit(1 if failed else 0)
