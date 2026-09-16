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
  await page.getByRole("button", { name: "Validate mapping", exact: true }).click();
  await page.getByRole("status").waitFor();
  const listScrolls = await page.evaluate(() => {
    return [".sm-source-list", ".sm-task-groups"].map(selector => {
      const region = document.querySelector(selector);
      region.scrollTop = region.scrollHeight;
      return region.scrollTop > 0;
    });
  });
  if (listScrolls.some(value => !value)) throw new Error("Long lists must scroll internally");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Zoom mapping in" }).click();
  await page.getByRole("region", { name: "Mapping diagram" }).getByRole("button", { name: /Validate preparation/ }).click();
  await page.getByRole("dialog", { name: "Source mapping inspector" }).waitFor();
  await page.getByRole("button", { name: "Done", exact: true }).click();
  const scrolledPage = await page.evaluate(() => [document.documentElement, document.body, document.querySelector(".workspace")].some(el => el.scrollTop !== 0 || el.scrollLeft !== 0));
  if (scrolledPage) throw new Error("Reaching internal content scrolled the page");
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
  return { viewportChecks: results.length, internalScrollAndDialogChecks: "passed" };
}
