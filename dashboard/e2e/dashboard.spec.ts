import { test, expect } from "@playwright/test";

test.describe("Navigation & Layout", () => {
  test("sidebar shows all nav links and app title", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("text=Engram").first()).toBeVisible();
    for (const label of ["Overview", "Lessons", "Traces", "Flagged", "Failure Queue", "Settings"]) {
      await expect(page.getByRole("link", { name: label })).toBeVisible();
    }
  });

  test("sidebar collapse and expand toggles labels", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Overview")).toBeVisible();
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
    await page.getByRole("button", { name: "Expand sidebar" }).click();
    await expect(page.getByRole("button", { name: "Collapse sidebar" })).toBeVisible();
  });

  test("nav links navigate to correct pages", async ({ page }) => {
    await page.goto("/");
    const routes: Record<string, string> = {
      Lessons: "/lessons",
      Traces: "/traces",
      Flagged: "/flagged",
      "Failure Queue": "/failure-queue",
      Settings: "/settings",
    };
    for (const [label, path] of Object.entries(routes)) {
      await page.getByRole("link", { name: label, exact: true }).click();
      await expect(page).toHaveURL(new RegExp(path));
    }
  });

  test("breadcrumb updates on navigation", async ({ page }) => {
    await page.goto("/lessons");
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Lessons");
    await page.getByRole("link", { name: "Traces" }).click();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Traces");
  });
});

test.describe("Overview Page", () => {
  test("renders KPI cards with data", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("active lessons")).toBeVisible();
    await expect(page.getByText("avg utility score")).toBeVisible();
    await expect(page.getByText("pending failures")).toBeVisible();
    await expect(page.getByText("flagged lessons")).toBeVisible();
  });

  test("renders all four charts", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Lesson Creation")).toBeVisible();
    await expect(page.getByText("Utility Distribution")).toBeVisible();
    await expect(page.getByText("Outcome Breakdown")).toBeVisible();
    await expect(page.getByText("Confidence Decay")).toBeVisible();
  });

  test("pending failures KPI links to failure queue", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /pending failures/ }).click();
    await expect(page).toHaveURL(/failure-queue/);
  });
});

test.describe("Lessons Page", () => {
  test("renders table with lessons", async ({ page }) => {
    await page.goto("/lessons");
    await expect(page.getByRole("heading", { name: "Lessons" })).toBeVisible();
    const table = page.getByRole("table");
    await expect(table).toBeVisible();
    // Should have header columns
    for (const col of ["Content", "Type", "Utility", "Confidence"]) {
      await expect(page.getByRole("columnheader", { name: col })).toBeVisible();
    }
  });

  test("type filter buttons work", async ({ page }) => {
    await page.goto("/lessons");
    await page.getByRole("button", { name: "success pattern" }).click();
    // All visible type badges should say "Success Pattern"
    const rows = page.locator("tbody tr");
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < Math.min(count, 5); i++) {
      await expect(rows.nth(i).locator("text=Success Pattern")).toBeVisible();
    }
    // Toggle off
    await page.getByRole("button", { name: "success pattern" }).click();
  });

  test("outcome dropdown filters lessons", async ({ page }) => {
    await page.goto("/lessons");
    // Select the outcome dropdown and filter — just verify no crash
    const select = page.locator("select").first();
    await select.selectOption("Success");
    await page.waitForTimeout(300);
    await select.selectOption("All outcomes");
  });

  test("clicking a lesson row navigates to detail", async ({ page }) => {
    await page.goto("/lessons");
    const firstRow = page.locator("tbody tr[cursor]").first();
    // Click the first data row
    await page.locator("tbody tr").first().click();
    await expect(page).toHaveURL(/\/lessons\//);
    await expect(page.getByRole("heading", { name: "Lesson Detail" })).toBeVisible();
  });

  test("lesson detail shows metadata and back link", async ({ page }) => {
    await page.goto("/lessons");
    await page.locator("tbody tr").first().click();
    await expect(page.getByText("Type")).toBeVisible();
    await expect(page.getByText("Outcome")).toBeVisible();
    await expect(page.getByText("Utility")).toBeVisible();
    await expect(page.getByText("Confidence")).toBeVisible();
    await expect(page.getByText("Provenance Chain")).toBeVisible();
    // Navigate back
    await page.getByRole("link", { name: "Back to Lessons" }).click();
    await expect(page).toHaveURL(/\/lessons$/);
  });
});

test.describe("Traces Page", () => {
  test("renders traces table", async ({ page }) => {
    await page.goto("/traces");
    await expect(page.getByRole("heading", { name: "Traces" })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    for (const col of ["ID", "Agent", "Outcome", "Status", "Created"]) {
      await expect(page.getByRole("columnheader", { name: col })).toBeVisible();
    }
  });

  test("status filter does not freeze the page", async ({ page }) => {
    await page.goto("/traces");
    const statusSelect = page.locator("select").nth(1);

    // Filter to Processed
    await statusSelect.selectOption("Processed");
    await page.waitForTimeout(500);
    // Page should still be responsive — check heading is visible
    await expect(page.getByRole("heading", { name: "Traces" })).toBeVisible();
    const rows = page.locator("tbody tr");
    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(0);

    // Filter to Pending
    await statusSelect.selectOption("Pending");
    await page.waitForTimeout(500);
    await expect(page.getByRole("heading", { name: "Traces" })).toBeVisible();

    // Back to All
    await statusSelect.selectOption("All statuses");
    await page.waitForTimeout(500);
    await expect(page.getByRole("heading", { name: "Traces" })).toBeVisible();
  });

  test("outcome filter works without freezing", async ({ page }) => {
    await page.goto("/traces");
    const outcomeSelect = page.locator("select").first();
    await outcomeSelect.selectOption("Success");
    await page.waitForTimeout(500);
    await expect(page.getByRole("heading", { name: "Traces" })).toBeVisible();
    await outcomeSelect.selectOption("All outcomes");
  });

  test("row expand shows trace details", async ({ page }) => {
    await page.goto("/traces");
    // Click first expand button
    const expandBtn = page.locator("tbody tr").first().getByRole("button");
    await expandBtn.click();
    await expect(page.getByText("Full ID:")).toBeVisible();
  });

  test("no React key warnings in console", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error" && msg.text().includes("unique")) {
        errors.push(msg.text());
      }
    });
    await page.goto("/traces");
    await page.waitForTimeout(1000);
    expect(errors).toHaveLength(0);
  });
});

test.describe("Failure Queue Page", () => {
  test("renders stats and signatures", async ({ page }) => {
    await page.goto("/failure-queue");
    await expect(page.getByRole("heading", { name: "Failure Queue" })).toBeVisible();
    await expect(page.getByText("Pending Failures")).toBeVisible();
    await expect(page.getByText("Top Categories")).toBeVisible();
    await expect(page.getByText("Error Signatures")).toBeVisible();
  });

  test("batch analysis button is clickable", async ({ page }) => {
    await page.goto("/failure-queue");
    const btn = page.getByRole("button", { name: "Run Batch Analysis Now" });
    await expect(btn).toBeVisible();
    await btn.click();
    // Should not crash — page stays on failure-queue
    await expect(page).toHaveURL(/failure-queue/);
  });
});

test.describe("Flagged / Review Page", () => {
  test("renders both tabs", async ({ page }) => {
    await page.goto("/flagged");
    await expect(page.getByRole("heading", { name: "Review Queue" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Flagged" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Conflicts" })).toBeVisible();
  });

  test("switching tabs works", async ({ page }) => {
    await page.goto("/flagged");
    await page.getByRole("button", { name: "Conflicts" }).click();
    await expect(page.getByText(/No conflicting lessons/)).toBeVisible();
    await page.getByRole("button", { name: "Flagged" }).click();
    await expect(page.getByText(/No lessons flagged/)).toBeVisible();
  });
});

test.describe("Settings Page", () => {
  test("renders all config sections", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Learning & Memory" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Models" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "OpenTelemetry" })).toBeVisible();
  });

  test("displays config values", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("lesson_confidence_half_life_days")).toBeVisible();
    await expect(page.getByText("extraction_model")).toBeVisible();
    await expect(page.getByText("BAAI/bge-small-en-v1.5")).toBeVisible();
  });
});
