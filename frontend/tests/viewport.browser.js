// Run against an isolated dev store:
// playwright-cli -s=layout run-code --filename frontend/tests/viewport.browser.js
// oxlint-disable-next-line no-unused-expressions -- Playwright CLI invokes this function expression.
async (page) => {
  const origin = await page.evaluate(() => location.origin);
  const results = [];
  const routes = ["workflow", "source-mapping", "review", "execution", "mailbox", "records"];
  const sizes = [[1920, 1080], [1440, 900], [1280, 720], [1024, 600], [800, 600], [390, 844], [900, 450]];

  for (const route of routes) {
    await page.goto(`${origin}/#${route}`);
    await page.locator(".app-shell").waitFor();
    // Core-backed pages and the workflow ResizeObserver need one short settle period.
    await page.waitForTimeout(250);
    for (const [width, height] of sizes) {
      await page.setViewportSize({ width, height });
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await page.waitForTimeout(75);
      const layout = await page.evaluate(() => {
        const selectors = ["html", "body", "#root", ".app-shell", ".workspace"];
        const overflow = selectors.flatMap((selector) => {
          const element = document.querySelector(selector);
          if (!element) return [];
          return element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1
            ? [{ selector, client: [element.clientWidth, element.clientHeight], scroll: [element.scrollWidth, element.scrollHeight] }]
            : [];
        });
        const regions = [...document.querySelectorAll("main > section, main > aside")]
          .map((element) => {
            const rect = element.getBoundingClientRect();
            return { name: element.className, width: rect.width, height: rect.height, bottom: rect.bottom, right: rect.right };
          })
          .filter((region) => region.width > 1 && region.height > 1);
        return { overflow, regions };
      });
      results.push({ route, width, height, ...layout });
      if (layout.overflow.length || layout.regions.some((region) =>
        region.height < 40 || region.width < 40 || region.bottom > height + 1 || region.right > width + 1)) {
        throw new Error(JSON.stringify(results.at(-1)));
      }
    }
  }

  // One candidate stream, one mapping column: uploads and mailbox drafts map
  // inline and a task expands in place. No dialog is ever opened.
  await page.goto(`${origin}/#source-mapping`);
  await page.setViewportSize({ width: 1024, height: 600 });
  await page.locator(".sm-stages .sm-stage").first().waitFor();
  const stageCount = await page.locator(".sm-stages .sm-stage").count();
  if (stageCount !== 5) throw new Error(`Expected five pipeline stages, found ${stageCount}`);
  const sourceCard = page.locator(".sm-source-card").first();
  if (await sourceCard.count()) {
    await sourceCard.click();
    await page.locator(".sm-map-row.is-focused").first().waitFor();
  }
  const conflictFilter = page.locator(".sm-map-filters button").nth(2);
  await conflictFilter.click();
  await page.locator(".sm-map-filters button.is-on").waitFor();
  await page.locator(".sm-map-filters button").first().click();
  const firstTask = page.locator(".sm-task-row").first();
  if (await firstTask.count()) {
    await firstTask.click();
    await page.locator(".sm-task-detail").waitFor();
    await page.keyboard.press("Escape");
  }
  const intakeDialogs = await page.locator("dialog[open]").count();
  if (intakeDialogs) throw new Error("Intake must not open modal dialogs for mapping or evidence");

  // Short-window lists either fit or own their scrolling; page chrome never scrolls.
  await page.setViewportSize({ width: 900, height: 450 });
  const intakeRegions = await page.evaluate(() => {
    const read = (selector) => {
      const region = document.querySelector(selector);
      if (!region) return { exists: false };
      region.scrollTop = region.scrollHeight;
      return {
        exists: true,
        overflows: region.scrollHeight > region.clientHeight + 1,
        reachable: region.scrollHeight <= region.clientHeight + 1 || region.scrollTop > 0,
      };
    };
    return {
      sources: read(".sm-source-list"),
      tasks: read(".sm-task-list"),
      mapping: read(".sm-mapping .sm-flow"),
      pageScrolled: [document.documentElement, document.body, document.querySelector(".workspace")]
        .filter(Boolean).some((element) => element.scrollTop !== 0 || element.scrollLeft !== 0),
    };
  });
  if (!intakeRegions.sources.reachable || !intakeRegions.tasks.reachable
      || !intakeRegions.mapping.reachable || intakeRegions.pageScrolled) {
    throw new Error(`Intake regions must remain internally reachable: ${JSON.stringify(intakeRegions)}`);
  }

  // Review's mobile tabs expose all three bounded workbench regions.
  await page.goto(`${origin}/#review`);
  await page.setViewportSize({ width: 900, height: 450 });
  for (const name of ["Preparations", "Message", "Readiness"]) {
    await page.getByRole("button", { name, exact: true }).click();
    const selected = await page.getByRole("button", { name, exact: true }).evaluate((element) =>
      element.classList.contains("active"));
    if (!selected) throw new Error(`Review tab did not become active: ${name}`);
  }

  // The workflow stage stays bounded inside the short window.
  await page.goto(`${origin}/#workflow`);
  await page.setViewportSize({ width: 900, height: 450 });
  await page.locator(".workflow-stage").waitFor();
  const stageFits = await page.locator(".workflow-stage").evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return rect.top >= -1 && rect.bottom <= innerHeight + 1;
  });
  if (!stageFits) throw new Error("Workflow stage must remain inside the short window");
  return { viewportChecks: results.length, interactionChecks: "passed" };
}
