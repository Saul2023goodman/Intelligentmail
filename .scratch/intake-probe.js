async (page) => {
  const origin = await page.evaluate(() => location.origin);
  await page.goto(`${origin}/#source-mapping`);
  await page.waitForTimeout(800);
  return await page.evaluate(() => {
    const button = document.querySelector(".sm-add-source");
    return {
      hash: location.hash,
      disabled: button?.disabled ?? null,
      scopeText: document.querySelector(".workspace-scope-indicator")?.textContent ?? "",
      students: document.body.textContent?.includes("尚未选择学生") ?? null,
    };
  });
}
