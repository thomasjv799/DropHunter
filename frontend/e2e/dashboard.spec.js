import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore with sample data" }).click();
  await expect(
    page.getByText("1–10 of 100 games", { exact: true }),
  ).toBeVisible();
});

test("100 games paginate, search, select, and change date range", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Celeste", exact: true }).click();
  await expect(page.getByRole("img")).toHaveAttribute(
    "aria-label",
    "Celeste: 60 recorded prices in 30 days",
  );
  await page.getByRole("button", { name: "7 days", exact: true }).click();
  await expect(page.getByRole("img")).toHaveAttribute(
    "aria-label",
    "Celeste: 14 recorded prices in 7 days",
  );
  await page.getByRole("button", { name: "Next →", exact: true }).click();
  await expect(
    page.getByText("11–20 of 100 games", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search tracked games" })
    .fill("No such game");
  await expect(
    page.getByText("No matching games", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search tracked games" })
    .fill("Hades");
  await expect(page.getByText("1–1 of 1 games", { exact: true })).toBeVisible();
});

test("editing target updates selected chart", async ({ page }) => {
  await page.getByRole("button", { name: "Celeste", exact: true }).click();
  page.once("dialog", (dialog) => dialog.accept("999"));
  await page
    .getByRole("button", { name: "Edit target for Celeste", exact: true })
    .click();
  await expect(page.getByText("Target: ₹999", { exact: true })).toBeVisible();
});

test("game limit rejects addition and removal allows confirmed addition", async ({
  page,
}) => {
  await page
    .getByRole("button", { name: "+ Track a game", exact: true })
    .click();
  await page.getByLabel("Game title", { exact: true }).fill("New test game");
  await page.getByRole("button", { name: "Find game", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm and track", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("100 games");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Remove Celeste", exact: true })
    .click();
  await expect(
    page.getByText("1–10 of 99 games", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "+ Track a game", exact: true })
    .click();
  await page.getByLabel("Game title", { exact: true }).fill("New test game");
  await page.getByRole("button", { name: "Find game", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm and track", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByText("1–10 of 100 games", { exact: true }),
  ).toBeVisible();
});

test("mobile view stays within viewport and preferences save", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Settings", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByLabel("Notification email", { exact: true })
    .fill("demo@example.com");
  await page
    .getByRole("button", { name: "Save preferences", exact: true })
    .click();
  await expect(
    page.getByText("Preferences saved.", { exact: true }),
  ).toBeVisible();
});
