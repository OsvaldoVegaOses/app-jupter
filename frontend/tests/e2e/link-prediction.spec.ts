/**
 * @fileoverview E2E: Link Prediction (axial) flow.
 *
 * Verifica que el panel:
 * - llama /api/axial/predict con project + parámetros
 * - renderiza sugerencias
 * - permite guardar predicciones (POST /api/link-prediction/save)
 * - llama /api/axial/community-links y actualiza la tabla
 */

import { test, expect } from "@playwright/test";

async function authenticate(page: any, request: any) {
  const email = `e2e_${Date.now()}_${Math.random().toString(16).slice(2)}@example.com`;
  const password = "Passw0rd!12345";

  const response = await request.post("/api/auth/register", {
    data: {
      email,
      password,
      full_name: "E2E Tester",
      organization_id: "default_org",
    },
  });

  if (!response.ok()) {
    const body = await response.text().catch(() => "");
    throw new Error(`E2E auth failed: ${response.status()} ${body}`);
  }

  const data = await response.json();
  const user = {
    id: data.user?.id,
    email: data.user?.email,
    name: data.user?.full_name ?? null,
    org_id: data.user?.organization_id,
    role: data.user?.role ?? "viewer",
  };

  await page.addInitScript(
    ({ accessToken, refreshToken, userJson }) => {
      window.localStorage.setItem("access_token", accessToken);
      if (refreshToken) {
        window.localStorage.setItem("refresh_token", refreshToken);
      }
      window.localStorage.setItem("qualy-auth-user", userJson);
    },
    {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      userJson: JSON.stringify(user),
    }
  );
}

test.describe("Link Prediction (Axial)", () => {
  test("renders suggestions and can save", async ({ page, request }) => {
    await authenticate(page, request);

    const projectId = "default";

    // Open directly in Investigación → Axial.
    await page.addInitScript(({ project }) => {
      window.localStorage.setItem("qualy-dashboard-view", "investigacion");
      window.localStorage.setItem("qualy-dashboard-investigation-view", "axial");
      window.localStorage.setItem("qualy-dashboard-project", project);
    }, { project: projectId });

    // Prevent the validation panel from depending on backend state.
    await page.route("**/api/link-predictions**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          total: 0,
          limit: 50,
          offset: 0,
          stats: {
            totals: { pendiente: 0, validado: 0, rechazado: 0 },
            by_algorithm: {},
            total: 0,
          },
        }),
      });
    });

    // Stub predict + community endpoints deterministically.
    await page.route("**/api/axial/predict**", async (route) => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get("project")).toBe(projectId);
      expect(url.searchParams.get("algorithm")).toBeTruthy();
      expect(url.searchParams.get("top_k")).toBeTruthy();

      const algorithm = url.searchParams.get("algorithm") || "common_neighbors";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          algorithm,
          project: projectId,
          suggestions: [
            { source: "codigo_a", target: "codigo_b", score: 0.9 },
            { source: "codigo_c", target: "codigo_d", score: 0.7 },
          ],
        }),
      });
    });

    await page.route("**/api/axial/community-links**", async (route) => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get("project")).toBe(projectId);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          method: "community_based",
          project: projectId,
          suggestions: [{ source: "codigo_x", target: "codigo_y", score: 1.0 }],
        }),
      });
    });

    await page.route("**/api/link-prediction/save", async (route) => {
      const raw = route.request().postData() || "{}";
      const body = JSON.parse(raw);
      expect(body.project).toBe(projectId);
      expect(Array.isArray(body.suggestions)).toBeTruthy();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, saved_count: (body.suggestions || []).length }),
      });
    });

    await page.goto("/");

    await expect(page.locator(".link-prediction-panel")).toBeVisible({ timeout: 10000 });

    // Predict suggestions.
    await page.locator('button:has-text("Predecir")').click();
    const rows = page.locator(".link-prediction-panel__table tbody tr");
    await expect(rows).toHaveCount(2, { timeout: 10000 });

    // Save suggestions.
    await page.locator('button:has-text("Guardar Predicciones")').click();
    await expect(page.locator(".link-prediction-panel__success")).toContainText("2", { timeout: 10000 });

    // Community-based suggestions.
    await page.locator('button:has-text("Por Comunidades")').click();
    await expect(rows).toHaveCount(1, { timeout: 10000 });
  });
});

