// Run against an isolated dev store:
// playwright-cli -s=layout run-code --filename frontend/tests/viewport.browser.js
// oxlint-disable-next-line no-unused-expressions -- Playwright CLI invokes this function expression.
async (page) => {
  const origin = await page.evaluate(() => location.origin);
  const results = [];
  for (const route of ["workflow", "tasks", "source-mapping"]) {
    await page.goto(`${origin}/#${route}`);
    for (const [width, height] of [[1920, 1080], [1440, 900], [1280, 720], [1024, 600], [800, 600], [390, 844], [900, 450]]) {
      await page.setViewportSize({ width, height });
      // Allow ResizeObserver and React to settle after the viewport changes.
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const layout = await page.evaluate(() => {
        const selectors = ["html", "body", "#root", ".app-shell", ".workspace", "main"];
        const overflow = selectors.flatMap(selector => {
          const el = document.querySelector(selector);
          return el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1
            ? [{ selector, client: [el.clientWidth, el.clientHeight], scroll: [el.scrollWidth, el.scrollHeight] }] : [];
        });
        const regions = [...document.querySelectorAll("main > section, main > aside")].map(el => {
          const rect = el.getBoundingClientRect();
          return { name: el.className, width: rect.width, height: rect.height, bottom: rect.bottom, right: rect.right };
        });
        return { overflow, regions };
      });
      results.push({ route, width, height, ...layout });
      if (layout.overflow.length || layout.regions.some(r => r.height < 40 || r.width < 40 || r.bottom > height + 1 || r.right > width + 1)) {
        throw new Error(JSON.stringify(results.at(-1)));
      }
    }
  }
  await page.setViewportSize({ width: 1024, height: 600 });
  // Student switching lives in the top bar.
  await page.getByRole("group", { name: "Switch student" }).getByRole("button", { name: /Mei Zhang/ }).click();
  // Classify an unresolved raw source into the Attachments category.
  const countSources = () => page.evaluate(() => ({
    unresolved: document.querySelectorAll(".sm-source-list .sm-source-card").length,
    attached: document.querySelectorAll('.sm-category-card[data-category="attachments"] .sm-file-chip:not(.is-empty)').length,
  }));
  const before = await countSources();
  await page.locator(".sm-source-card").filter({ hasText: /transcript/i }).first().click();
  await page.locator('.sm-category-card[data-category="attachments"] .sm-classify-btn').click();
  await page.getByRole("status").waitFor();
  const after = await countSources();
  if (after.unresolved !== before.unresolved - 1 || after.attached !== before.attached + 1) {
    throw new Error(`Classification must move the raw source into its category: ${JSON.stringify({ before, after })}`);
  }
  // Missing-email supervisors remain visible as grey incomplete rows.
  const incomplete = await page.locator(".sm-task-row.is-incomplete", { hasText: "Sophie Lee" }).count();
  if (incomplete !== 1) throw new Error("A supervisor without an email must remain visible as an incomplete task");
  // Per-task attachment overrides live in the on-demand task inspector.
  await page.locator(".sm-task-row:not(.is-incomplete)").first().click();
  const taskDialog = page.getByRole("dialog", { name: "Resolved task inspector" });
  await taskDialog.waitFor();
  await taskDialog.getByRole("checkbox").first().uncheck();
  await taskDialog.getByText(/per-task override/).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await taskDialog.getByRole("button", { name: "Done", exact: true }).click();
  const scrolledPage = await page.evaluate(() => [document.documentElement, document.body, document.querySelector(".workspace")].some(el => el.scrollTop !== 0 || el.scrollLeft !== 0));
  if (scrolledPage) throw new Error("Reaching internal content scrolled the page");
  // In a short window the source/task lists scroll internally and the fixed
  // category column never scrolls; all six categories stay reachable.
  await page.setViewportSize({ width: 900, height: 450 });
  const listCheck = await page.evaluate(() => {
    const read = selector => {
      const region = document.querySelector(selector);
      region.scrollTop = region.scrollHeight;
      return { canScroll: region.scrollTop > 0, overflows: region.scrollHeight > region.clientHeight + 1 };
    };
    const sources = read(".sm-source-list");
    const tasks = read(".sm-task-list");
    const categories = read(".sm-category-list");
    const region = document.querySelector(".sm-category-list").getBoundingClientRect();
    const cards = [...document.querySelectorAll(".sm-category-card")].map(el => {
      const rect = el.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom };
    });
    const cardsReachable = cards.every(rect => rect.top >= region.top - 1 && rect.bottom <= region.bottom + 1);
    return { sources, tasks, categories, cardsReachable };
  });
  if (!listCheck.sources.canScroll || !listCheck.tasks.canScroll) {
    throw new Error(`Source and task lists must scroll internally: ${JSON.stringify(listCheck)}`);
  }
  if (listCheck.categories.overflows || !listCheck.cardsReachable) {
    throw new Error(`Center category column must fit without scrolling: ${JSON.stringify(listCheck)}`);
  }
  await page.goto(`${origin}/#workflow`);
  await page.setViewportSize({ width: 900, height: 450 });
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Workflow guide" }).click();
  await page.getByRole("dialog").waitFor();
  const dialogFits = await page.getByRole("dialog").evaluate(el => {
    const rect = el.getBoundingClientRect();
    el.scrollTop = el.scrollHeight;
    return rect.top >= 0 && rect.bottom <= innerHeight && el.scrollTop > 0;
  });
  if (!dialogFits) throw new Error("Short-window dialog must fit and scroll internally");
  await page.keyboard.press("Escape");
  return { viewportChecks: results.length, interactionChecks: "passed" };
}
