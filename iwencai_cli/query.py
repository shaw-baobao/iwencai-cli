from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from . import DEFAULT_PROFILE_DIR


RESULT_URL_TEMPLATE = "https://www.iwencai.com/unifiedwap/result?w={q}&querytype=stock"


def query_iwencai(
    question: str,
    *,
    headless: bool = True,
    profile_dir: Optional[str] = None,
    wait_ms: int = 4000,
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

        # Scroll the result table horizontally to trigger lazy-rendered header columns
        try:
            page_obj.evaluate(
                """() => {
                    const scrollers = document.querySelectorAll('.iwc-table-content, [class*=scroll], .m-table-body');
                    for (const s of scrollers) {
                        if (s.scrollWidth > s.clientWidth) {
                            s.scrollLeft = s.scrollWidth;
                        }
                    }
                }"""
            )
            page_obj.wait_for_timeout(1500)
            page_obj.evaluate(
                """() => {
                    const scrollers = document.querySelectorAll('.iwc-table-content, [class*=scroll], .m-table-body');
                    for (const s of scrollers) s.scrollLeft = 0;
                }"""
            )
            page_obj.wait_for_timeout(500)
        except Exception:
            pass

        # Detect "no results"
        body_text = page_obj.inner_text("body")
        if "未选出" in body_text or "抱歉，未选出" in body_text:
            ctx.close()
            return {"rows": [], "count": 0, "headers": [], "raw_text": body_text[:500]}

        # iWenCai renders results as multiple parallel tables (fixed left
        # columns + scrollable right columns). Each table has N <tr>s, and
        # we need to merge the i-th row across all tables to get a full row.
        rows_data = page_obj.evaluate(
            """
            () => {
                const allTables = Array.from(document.querySelectorAll('table'));
                let tables = allTables
                    .map(t => ({
                        el: t,
                        rows: Array.from(t.querySelectorAll('tbody tr')),
                    }))
                    .filter(t => t.rows.length >= 2);
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
        )
        ctx.close()

    if not rows_data:
        return {"rows": [], "count": 0, "headers": []}

    return {
        "rows": rows_data.get("rows", []),
        "count": len(rows_data.get("rows", [])),
        "headers": rows_data.get("headers", []),
    }


def parse_results(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    return raw.get("rows", []) if isinstance(raw, dict) else []
