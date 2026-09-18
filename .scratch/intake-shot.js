// oxlint-disable-next-line no-unused-expressions -- Playwright CLI invokes this function expression.
async (page) => {
(async () => {
  const shot = async (name) => {
    await page.screenshot({ path: `.scratch/out/${name}.png` });
  };
  await page.goto("http://127.0.0.1:5179/#source-mapping");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator(".sm-stages .sm-stage").first().waitFor();
  await page.waitForTimeout(600);
  await shot("intake-unified-1440");

  // Select the first observed draft so its mapping row highlights.
  const draftCard = page.locator(".sm-source-card.is-draft").first();
  if (await draftCard.count()) {
    await draftCard.click();
    await page.waitForTimeout(200);
    await shot("intake-draft-focused-1440");
  }

  // Tick the importable drafts and show the pending decision.
  const picks = page.locator(".sm-map-row .sm-map-pick input:not([disabled])");
  const count = await picks.count();
  for (let index = 0; index < count; index += 1) await picks.nth(index).check();
  await page.waitForTimeout(200);
  await shot("intake-draft-selected-1440");

  // Conflict filter isolates blocking rows.
  await page.locator(".sm-map-filters button").nth(2).click();
  await page.waitForTimeout(200);
  await shot("intake-conflict-filter-1440");
  await page.locator(".sm-map-filters button").first().click();

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.waitForTimeout(200);
  await shot("intake-unified-1280");
  return { draftCards: await page.locator(".sm-source-card.is-draft").count(), importable: count };
}
