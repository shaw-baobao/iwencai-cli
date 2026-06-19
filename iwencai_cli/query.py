from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote

from . import DEFAULT_PROFILE_DIR


RESULT_URL_TEMPLATE = "https://www.iwencai.com/unifiedwap/result?w={q}&querytype=stock"

SCROLL_TABLES_SCRIPT = """
() => {
    const scrollers = document.querySelectorAll('.iwc-table-content, [class*=scroll], .m-table-body');
    for (const s of scrollers) {
        if (s.scrollWidth > s.clientWidth) {
            s.scrollLeft = s.scrollWidth;
        }
    }
}
"""

RESET_TABLE_SCROLL_SCRIPT = """
() => {
    const scrollers = document.querySelectorAll('.iwc-table-content, [class*=scroll], .m-table-body');
    for (const s of scrollers) s.scrollLeft = 0;
}
"""

SCRAPE_TABLE_SCRIPT = """
() => {
    const allTables = Array.from(document.querySelectorAll('table'));
    let tables = allTables
        .map(t => ({
            el: t,
            rows: Array.from(t.querySelectorAll('tbody tr')),
        }))
        .filter(t => t.rows.length >= 1);
    if (!tables.length) return null;

    tables.forEach(t => {
        const rect = t.el.getBoundingClientRect();
        t.x = rect.left;
    });
    tables.sort((a, b) => a.x - b.x);

    const rowCount = Math.max(...tables.map(t => t.rows.length));
    tables = tables.filter(t => t.rows.length === rowCount);

    // iWenCai often renders a duplicate fixed-left table overlaid
    // for sticky columns. De-dup: drop tables whose first data row
    // is a prefix of another table's first data row.
    const firstRowTexts = tables.map(t =>
        Array.from(t.rows[0].cells).map(c => c.innerText.trim()).join('|')
    );
    const keep = new Array(tables.length).fill(true);
    for (let i = 0; i < tables.length; i++) {
        for (let j = 0; j < tables.length; j++) {
            if (i === j || !keep[j]) continue;
            if (firstRowTexts[j].startsWith(firstRowTexts[i])
                && firstRowTexts[j] !== firstRowTexts[i]) {
                keep[i] = false;
                break;
            }
        }
    }
    tables = tables.filter((_, i) => keep[i]);

    // Build merged data rows
    const dataRows = [];
    for (let i = 0; i < rowCount; i++) {
        const merged = [];
        for (const t of tables) {
            const tr = t.rows[i];
            if (tr) merged.push(...Array.from(tr.cells));
        }
        dataRows.push(merged);
    }

    // Headers live in .iwc-table-header > ul > li.
    // Multiple header containers overlap; pair each by matching
    // column count with the data tables.
    const headerContainers = Array.from(
        document.querySelectorAll('.iwc-table-header')
    ).map(el => {
        const lis = Array.from(el.querySelectorAll('ul > li'));
        return {
            el,
            items: lis.map(li => li.innerText.trim().replace(/\\s+/g, ' ')),
        };
    });

    // Sort header containers: smaller-width (fixed-left) first,
    // then wider (scrollable right) to match data column order
    headerContainers.sort((a, b) => {
        const wa = a.el.getBoundingClientRect().width;
        const wb = b.el.getBoundingClientRect().width;
        return wa - wb;
    });
    const allHeaders = [];
    for (const hc of headerContainers) {
        allHeaders.push(...hc.items);
    }

    const data = [];
    for (const cells of dataRows) {
        const obj = {};
        cells.forEach((c, idx) => {
            const key = allHeaders[idx] || `col${idx}`;
            obj[key] = c.innerText.trim().replace(/\\s+/g, ' ');
        });
        data.push(obj);
    }
    return { headers: allHeaders, rows: data };
}
"""

RESULT_SIGNATURE_SCRIPT = """
() => {
    const rows = Array.from(document.querySelectorAll('table tbody tr'))
        .map(row => Array.from(row.cells).map(c => c.innerText.trim()).join('|'))
        .filter(Boolean);
    return rows.slice(0, 5).join('||');
}
"""

RESULT_SIGNATURE_CHANGED_SCRIPT = """
previous => {
    const rows = Array.from(document.querySelectorAll('table tbody tr'))
        .map(row => Array.from(row.cells).map(c => c.innerText.trim()).join('|'))
        .filter(Boolean);
    const signature = rows.slice(0, 5).join('||');
    return Boolean(signature) && signature !== previous;
}
"""

NEXT_PAGE_SCRIPT = """
() => {
    const normalize = value => (value || '').replace(/\\s+/g, '');
    const isVisible = el => {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0
            && rect.height > 0
            && style.display !== 'none'
            && style.visibility !== 'hidden';
    };
    const isDisabled = el => {
        for (let node = el; node && node !== document.body; node = node.parentElement) {
            const cls = String(node.className || '');
            if (node.disabled
                || node.getAttribute('disabled') !== null
                || node.getAttribute('aria-disabled') === 'true'
                || /disabled|disable|pagination-disabled/i.test(cls)) {
                return true;
            }
            if (/pagination|pager/i.test(cls)) break;
        }
        return false;
    };
    const elements = Array.from(document.querySelectorAll('button, a, li, span, div'));
    const candidates = elements.filter(el => {
        const text = normalize(el.innerText);
        const label = normalize(
            el.getAttribute('aria-label')
            || el.getAttribute('title')
            || el.getAttribute('data-title')
            || ''
        );
        const cls = String(el.className || '');
        return text === '下一页'
            || label.includes('下一页')
            || label.toLowerCase().includes('next')
            || /(^|[-_\\s])next($|[-_\\s])|pagination-next|pager-next|btn-next|page-next|next-page/i.test(cls);
    });

    for (const el of candidates) {
        const clickable = el.closest('button,a') || el;
        if (!isVisible(clickable) || isDisabled(clickable)) continue;
        clickable.scrollIntoView({ block: 'center', inline: 'center' });
        clickable.click();
        return true;
    }
    return false;
}
"""


def query_iwencai(
    question: str,
    *,
    headless: bool = True,
    profile_dir: Optional[str] = None,
    wait_ms: int = 4000,
    max_pages: Optional[int] = None,
) -> Dict[str, Any]:
    """Open the iWenCai result page and scrape the stock table from the DOM.

    Returns {"rows": [...], "count": N, "headers": [...]}.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        raise RuntimeError("Playwright 未安装，请加 --install-playwright")

    profile_dir = profile_dir or str(DEFAULT_PROFILE_DIR)
    url = RESULT_URL_TEMPLATE.format(q=quote(question))

    with sync_playwright() as p:
        launch_kwargs = dict(
            user_data_dir=profile_dir,
            headless=headless,
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
            ignore_default_args=["--enable-automation"],
        )
        # Prefer the user's real Chrome if installed, fall back to bundled Chromium
        try:
            ctx = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
        except Exception:
            ctx = p.chromium.launch_persistent_context(**launch_kwargs)

        # Strip the navigator.webdriver flag on every page
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "window.chrome = window.chrome || { runtime: {} };"
        )

        try:
            page_obj = ctx.new_page()
            page_obj.goto(url, wait_until="load", timeout=30000)

            # Wait for either the results table or a "no results" message
            try:
                page_obj.wait_for_selector(
                    "table, text=未选出, text=抱歉",
                    timeout=20000,
                )
            except Exception:
                pass
            page_obj.wait_for_timeout(wait_ms)

            # Detect "no results"
            body_text = page_obj.inner_text("body")
            if "未选出" in body_text or "抱歉，未选出" in body_text:
                return {"rows": [], "count": 0, "headers": [], "raw_text": body_text[:500]}

            rows_data = _collect_result_pages(page_obj, wait_ms, max_pages)
        finally:
            ctx.close()

    if not rows_data:
        return {"rows": [], "count": 0, "headers": []}

    return {
        "rows": rows_data.get("rows", []),
        "count": len(rows_data.get("rows", [])),
        "headers": rows_data.get("headers", []),
        "pages": rows_data.get("pages", 0),
    }


def parse_results(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    return raw.get("rows", []) if isinstance(raw, dict) else []


def _collect_result_pages(
    page_obj: Any,
    wait_ms: int,
    max_pages: Optional[int],
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    headers: List[str] = []
    seen: Set[Tuple[Tuple[str, str], ...]] = set()
    pages = 0

    while max_pages is None or pages < max_pages:
        _prepare_table(page_obj)
        rows_data = page_obj.evaluate(SCRAPE_TABLE_SCRIPT)
        if not rows_data:
            break

        page_rows = rows_data.get("rows", [])
        if not headers:
            headers = rows_data.get("headers", [])
        _extend_unique_rows(rows, page_rows, seen)
        pages += 1

        if not page_rows:
            break

        signature = page_obj.evaluate(RESULT_SIGNATURE_SCRIPT)
        if not _goto_next_page(page_obj, signature, wait_ms):
            break

    return {"headers": headers, "rows": rows, "pages": pages}


def _prepare_table(page_obj: Any) -> None:
    # Horizontal scrolling triggers lazy-rendered header columns.
    try:
        page_obj.evaluate(SCROLL_TABLES_SCRIPT)
        page_obj.wait_for_timeout(1500)
        page_obj.evaluate(RESET_TABLE_SCROLL_SCRIPT)
        page_obj.wait_for_timeout(500)
    except Exception:
        pass


def _goto_next_page(page_obj: Any, signature: str, wait_ms: int) -> bool:
    try:
        clicked = page_obj.evaluate(NEXT_PAGE_SCRIPT)
    except Exception:
        return False

    if not clicked:
        return False

    try:
        page_obj.wait_for_function(
            RESULT_SIGNATURE_CHANGED_SCRIPT,
            signature,
            timeout=max(5000, wait_ms * 2),
        )
        return True
    except Exception:
        page_obj.wait_for_timeout(min(max(wait_ms, 1000), 3000))
        return page_obj.evaluate(RESULT_SIGNATURE_SCRIPT) != signature


def _extend_unique_rows(
    rows: List[Dict[str, Any]],
    page_rows: List[Dict[str, Any]],
    seen: Set[Tuple[Tuple[str, str], ...]],
) -> None:
    for row in page_rows:
        signature = tuple((str(key), str(value)) for key, value in sorted(row.items()))
        if signature in seen:
            continue
        seen.add(signature)
        rows.append(row)
