import { test, expect } from "@playwright/test";

test("chat page renders and validates empty input", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /RAG Chat/i })).toBeVisible();
  const button = page.getByRole("button", { name: /Отправить/ });
  await expect(button).toBeDisabled();
  await page.getByPlaceholder(/Спросите/).fill("С какого года?");
  await expect(button).toBeEnabled();
});
